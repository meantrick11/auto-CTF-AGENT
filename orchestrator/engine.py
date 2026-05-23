"""Main orchestrator — wires all components and drives the agent loop."""

import json
import os

from blackboard.blackboard import Blackboard
from commander.agent import Commander
from workers.base_worker import TaskResult
from workers.registry import get_worker_registry
from workers.web.agent import WebWorker
from hooks import fire


class Engine:
    """Central orchestrator managing the Commander-Worker-Blackboard loop.

    Hook points (7 total):
      before_plan, after_plan, before_task_create,
      before_execute, after_execute, on_finding, on_complete
    """

    def __init__(self, model: str | None = None,
                 max_rounds: int = 10, data_dir: str = "data"):
        self.model = model
        self.max_rounds = max_rounds
        self._data_dir = data_dir
        self.blackboard = Blackboard(data_dir=data_dir)
        self.commander = Commander(model=model)

        # Register domain workers in global registry
        reg = get_worker_registry()
        reg.register(WebWorker(model=model), name="web_worker",
                     domain="web", task_prefixes=["web_"])
        self._round = 0

    def run(self, goal: str) -> dict:
        """Execute the full agent loop for a given goal."""
        self._log(f"=== Mission Start ===")
        self._log(f"Goal: {goal}")

        # Phase 0: Clear old state
        filepath = os.path.join(self._data_dir, "blackboard.json")
        if os.path.exists(filepath):
            os.remove(filepath)
        self.blackboard = Blackboard(data_dir=self._data_dir)

        # Phase 1: Initialize
        self.blackboard.create_goal(goal)

        # Phase 2: Main loop
        for self._round in range(1, self.max_rounds + 1):
            self._log(f"\n--- Round {self._round}/{self.max_rounds} ---")

            # ── Hook: before_plan ──
            snapshot = self.blackboard.snapshot()
            ev = fire("before_plan", snapshot=snapshot, round=self._round)
            if ev.blocked:
                self._log(f"[BLOCKED] before_plan: {ev.block_reason}")
                return self._build_report("failed", ev.block_reason)

            decision = self.commander.plan(snapshot)

            # ── Hook: after_plan ──
            fire("after_plan", snapshot=snapshot, decision=decision, round=self._round)

            self._log(f"Commander decision: {decision.get('decision')}")
            self._log(f"Reasoning: {decision.get('reasoning', '')[:120]}")

            if decision["decision"] in ("completed", "failed"):
                self.blackboard.update_goal_status(decision["decision"])
                final_summary = decision.get("final_summary", "")
                self._log(f"\n=== Mission {decision['decision'].upper()} ===")
                self._log(final_summary)
                report = self._build_report(decision["decision"], final_summary)
                # ── Hook: on_complete ──
                fire("on_complete", outcome=decision["decision"], report=report)
                return report

            # Publish new tasks
            for task_def in decision.get("new_tasks", []):
                # ── Hook: before_task_create ──
                ev = fire("before_task_create", task_def=task_def)
                if ev.blocked:
                    self._log(f"[BLOCKED] before_task_create: {ev.block_reason}")
                    continue

                self.blackboard.create_task(
                    type=task_def["type"],
                    instruction=task_def["instruction"],
                    input_data=task_def.get("input_data", {}),
                )

            # Execute pending tasks
            pending = self.blackboard.get_pending_tasks()
            if not pending:
                self._log("No pending tasks — Commander did not create any.")
                continue

            for task in pending:
                self._execute_task(task)

        # Max rounds reached
        self._log(f"\n=== Max rounds ({self.max_rounds}) reached ===")
        self.blackboard.update_goal_status("failed")
        report = self._build_report("failed", "Max rounds reached without finding flag")
        fire("on_complete", outcome="failed", report=report)
        return report

    def _execute_task(self, task: dict):
        task_id = task["id"]
        task_type = task["type"]

        worker = self._route_task(task_type)
        if worker is None:
            self._log(f"No worker for task type: {task_type}, skipping task {task_id}")
            self.blackboard.complete_task(task_id, {"error": "No suitable worker"}, "failed")
            return

        self.blackboard.assign_task(task_id, worker.name)
        self.blackboard.start_task(task_id)

        # ── Hook: before_execute ──
        ev = fire("before_execute", task=task, worker_name=worker.name)
        if ev.blocked:
            self._log(f"[BLOCKED] before_execute: {ev.block_reason}")
            self.blackboard.complete_task(task_id, {"error": ev.block_reason}, "failed")
            return

        self._log(f"Executing [{task_type}] → {worker.name}: {task['instruction'][:100]}")

        result = worker.execute(task, self.blackboard.snapshot())

        # ── Hook: after_execute (Filter can modify result) ──
        ev = fire("after_execute", task=task, result=result)
        result = ev.data.get("result", result)

        # Normalize: TaskResult → dict access for uniform handling
        if isinstance(result, TaskResult):
            findings = result.findings
            status = result.status
            summary = result.summary
            output_data = result.output_data
        else:
            findings = result.get("findings", [])
            status = result.get("status", "completed")
            summary = result.get("summary", "")
            output_data = result.get("output_data", {})

        for finding in findings:
            if isinstance(finding, dict):
                finding["source_task_id"] = task_id
            else:
                finding.source_task_id = task_id

            # ── Hook: on_finding ──
            ev = fire("on_finding", finding=finding, task_id=task_id)
            if ev.blocked:
                continue

            # Convert to dict for blackboard (WorkerFinding → dict)
            if not isinstance(finding, dict):
                finding = {
                    "type": finding.type,
                    "title": finding.title,
                    "data": finding.data,
                    "confidence": finding.confidence,
                    "source_task_id": finding.source_task_id,
                }
            self.blackboard.add_finding(finding)
            self._log(f"  Finding: [{finding['type']}] {finding['title']}")

        # Complete task
        self.blackboard.complete_task(
            task_id,
            {
                "summary": summary,
                "raw_output": output_data,
            },
            status,
        )
        self._log(f"  Task {task_id}: {status}")

    def _route_task(self, task_type: str):
        reg = get_worker_registry()
        worker = reg.route(task_type)
        if worker is not None:
            return worker
        # Fallback: any worker willing to try
        return reg.get("web_worker")

    def _build_report(self, outcome: str, summary: str) -> dict:
        return {
            "outcome": outcome,
            "summary": summary,
            "total_rounds": self._round,
            "findings": self.blackboard.get_findings(),
            "flag": self._extract_flag(),
            "task_history": self.blackboard.get_all_tasks(),
            "event_log": self.blackboard.get_recent_events(100),
        }

    def _extract_flag(self) -> str:
        import re
        for f in self.blackboard.get_findings_by_type("flag"):
            data = f.get("data", {})
            for key in ("flag", "decoded", "value", "result"):
                if key in data and data[key]:
                    return str(data[key])
            for v in data.values():
                if isinstance(v, str):
                    m = re.search(r"(?:CTF|flag)\{[^\}]+\}", v, re.IGNORECASE)
                    if m:
                        return m.group(0)
        return ""

    def _log(self, msg: str):
        print(msg)
