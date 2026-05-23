"""Shared blackboard — the single source of truth for all agents."""

import json
import os
import tempfile

from blackboard.schema import (
    Goal, Task, Finding, EventLog,
    GoalStatus, TaskStatus, FindingType,
    _new_id, _now,
)


class Blackboard:
    """Centralized state store with JSON file persistence.

    All agents read/write through this single interface.
    No direct agent-to-agent communication.
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._filepath = os.path.join(data_dir, "blackboard.json")
        self._goal: Goal | None = None
        self._tasks: dict[str, Task] = {}
        self._findings: dict[str, Finding] = {}
        self._events: list[EventLog] = []
        self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(self._filepath):
            return
        with open(self._filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if raw.get("goal"):
            g = raw["goal"]
            if "status" in g and isinstance(g["status"], str):
                g["status"] = GoalStatus(g["status"])
            self._goal = Goal(**g)
        for t in raw.get("tasks", []):
            if "status" in t and isinstance(t["status"], str):
                t["status"] = TaskStatus(t["status"])
            task = Task(**t)
            self._tasks[task.id] = task
        for f_data in raw.get("findings", []):
            if "type" in f_data and isinstance(f_data["type"], str):
                f_data["type"] = FindingType(f_data["type"])
            finding = Finding(**f_data)
            self._findings[finding.id] = finding
        for e in raw.get("events", []):
            self._events.append(EventLog(**e))

    def _save(self):
        os.makedirs(self._data_dir, exist_ok=True)
        data = {
            "goal": self._goal.__dict__ if self._goal else None,
            "tasks": [t.__dict__ for t in self._tasks.values()],
            "findings": [f.__dict__ for f in self._findings.values()],
            "events": [e.__dict__ for e in self._events],
        }
        # Atomic write: temp file + rename
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, dir=self._data_dir
        )
        try:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.close()
            os.replace(tmp.name, self._filepath)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    # ── goal ─────────────────────────────────────────────────────

    def create_goal(self, description: str) -> Goal:
        self._goal = Goal(description=description, status=GoalStatus.RUNNING)
        self._add_event("engine", "goal_created", description)
        self._save()
        return self._goal

    def get_goal(self) -> dict | None:
        if self._goal is None:
            return None
        return self._goal.__dict__

    def update_goal_status(self, status: str):
        if self._goal is None:
            return
        self._goal.status = GoalStatus(status)
        self._add_event("commander", "goal_" + status, self._goal.description)
        self._save()

    # ── tasks ────────────────────────────────────────────────────

    def create_task(self, type: str, instruction: str,
                    input_data: dict | None = None) -> Task:
        task = Task(
            type=type,
            instruction=instruction,
            input_data=input_data or {},
            goal_id=self._goal.id if self._goal else "",
        )
        self._tasks[task.id] = task
        self._add_event("commander", "task_created",
                        f"{task.type}: {task.instruction[:80]}")
        self._save()
        return task

    def get_pending_tasks(self) -> list[dict]:
        return [t.__dict__ for t in self._tasks.values()
                if t.status == TaskStatus.PENDING]

    def assign_task(self, task_id: str, worker_name: str):
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = TaskStatus.ASSIGNED
        task.assigned_to = worker_name
        self._add_event("engine", "task_assigned",
                        f"{task_id} -> {worker_name}")
        self._save()

    def get_assigned_task(self, worker_name: str) -> dict | None:
        for t in self._tasks.values():
            if t.assigned_to == worker_name and t.status == TaskStatus.ASSIGNED:
                return t.__dict__
        return None

    def start_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = TaskStatus.RUNNING
        self._save()

    def complete_task(self, task_id: str, output_data: dict,
                      status: str = "completed"):
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = TaskStatus(status)
        task.output_data = output_data
        task.completed_at = _now()
        self._add_event(task.assigned_to or "worker", "task_" + status,
                        f"{task_id}: {task.instruction[:60]}")
        self._save()

    def get_task(self, task_id: str) -> dict | None:
        task = self._tasks.get(task_id)
        return task.__dict__ if task else None

    def get_all_tasks(self) -> list[dict]:
        return [t.__dict__ for t in self._tasks.values()]

    # ── findings ─────────────────────────────────────────────────

    def add_finding(self, finding_data: dict) -> Finding:
        finding = Finding(
            type=FindingType(finding_data["type"]),
            title=finding_data["title"],
            data=finding_data.get("data", {}),
            source_task_id=finding_data.get("source_task_id", ""),
            confidence=finding_data.get("confidence", 1.0),
        )
        self._findings[finding.id] = finding
        self._add_event("worker", "finding_added",
                        f"[{finding.type.value}] {finding.title}")
        self._save()
        return finding

    def get_findings(self) -> list[dict]:
        return [f.__dict__ for f in self._findings.values()]

    def get_findings_by_type(self, finding_type: str) -> list[dict]:
        return [f.__dict__ for f in self._findings.values()
                if f.type.value == finding_type]

    # ── events ───────────────────────────────────────────────────

    def _add_event(self, agent_name: str, action: str, detail: str = ""):
        self._events.append(EventLog(
            agent_name=agent_name, action=action, detail=detail
        ))

    def add_event(self, agent_name: str, action: str, detail: str = ""):
        self._add_event(agent_name, action, detail)
        self._save()

    def get_recent_events(self, n: int = 20) -> list[dict]:
        return [e.__dict__ for e in self._events[-n:]]

    # ── snapshot ─────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return full blackboard state for Commander planning."""
        return {
            "goal": self.get_goal(),
            "tasks": self.get_all_tasks(),
            "findings": self.get_findings(),
            "recent_events": self.get_recent_events(20),
        }
