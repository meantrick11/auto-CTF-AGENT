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
        self._situation_summary: dict | None = None
        self._compacted_finding_count: int = 0
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
        self._situation_summary = raw.get("situation_summary")
        self._compacted_finding_count = raw.get("compacted_finding_count", 0)

    def _save(self):
        os.makedirs(self._data_dir, exist_ok=True)
        data = {
            "goal": self._goal.__dict__ if self._goal else None,
            "tasks": [t.__dict__ for t in self._tasks.values()],
            "findings": [f.__dict__ for f in self._findings.values()],
            "events": [e.__dict__ for e in self._events],
            "situation_summary": self._situation_summary,
            "compacted_finding_count": self._compacted_finding_count,
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

    def add_finding(self, finding_data: dict) -> Finding | None:
        """Add a finding. On duplicates, boosts confidence of existing. Returns None if skipped."""
        ftype = finding_data["type"]
        ftitle = finding_data["title"]

        for existing in self._findings.values():
            if existing.type.value == ftype and existing.title == ftitle:
                # Boost confidence — same info from multiple sources = more reliable
                new_conf = finding_data.get("confidence", 1.0)
                boost = min(new_conf * 0.15, 0.3)  # max 0.3 boost per duplicate
                existing.confidence = min(existing.confidence + boost, 1.0)
                existing.data.setdefault("confirmed_by", 0)
                existing.data["confirmed_by"] += 1
                self._add_event("worker", "finding_confirmed",
                                f"[{ftype}] {ftitle} ↟ {existing.confidence:.2f}")
                self._save()
                return None

        finding = Finding(
            type=FindingType(ftype),
            title=ftitle,
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

    # ── compaction ───────────────────────────────────────────────

    def _needs_compact(self, threshold: int = 3000) -> bool:
        """Check if accumulated findings warrant LLM compaction."""
        if not self._findings:
            return False
        if len(self._findings) == self._compacted_finding_count:
            return False
        total = sum(len(str(f.data)) for f in self._findings.values())
        return total > threshold

    def compact(self, client, model: str = "deepseek-chat") -> None:
        """Generate a structured situation summary from all findings via LLM.

        Original findings are never modified — the summary is stored separately.
        """
        findings_for_llm = []
        for f in self._findings.values():
            findings_for_llm.append({
                "type": f.type.value,
                "title": f.title,
                "data": f.data,
                "confidence": f.confidence,
            })

        system_prompt = (
            "You are a CTF intelligence summarizer. Given findings from a "
            "penetration test, produce a concise situation report. "
            "Focus on actionable intelligence. Be brief — discard noise.\n\n"
            "IMPORTANT: Pay attention to failed tasks. If the same approach "
            "has been tried multiple times and failed, note it so the "
            "Commander doesn't repeat it.\n\n"
            "Output ONLY a JSON object:\n"
            "{\n"
            '  "summary": "one paragraph overview of current situation",\n'
            '  "flags": ["flag1", "flag2"],\n'
            '  "vulnerabilities": [{"name": "...", "location": "...", "confidence": 0.9}],\n'
            '  "assets": [{"url": "...", "note": "..."}],\n'
            '  "credentials": [{"user": "...", "source": "..."}],\n'
            '  "key_observations": ["observation 1"],\n'
            '  "dead_ends": ["approach X failed 3x — do not retry"],\n'
            '  "recommended_steps": ["suggestion 1"]\n'
            "}"
        )

        # Include failed task history so summary captures what NOT to retry
        failed_tasks = []
        for t in self.get_all_tasks():
            if t.get("status") == "failed":
                failed_tasks.append({
                    "type": t.get("type", ""),
                    "instruction": t.get("instruction", "")[:120],
                    "error": str(t.get("output_data", {}).get("error_detail", {}))
                             [:200],
                })

        user_message = "## Current Findings\n\n" + json.dumps(
            findings_for_llm, ensure_ascii=False, indent=2
        )
        if failed_tasks:
            user_message += "\n\n## Failed Tasks (avoid repeating these)\n" + (
                json.dumps(failed_tasks[-5:], ensure_ascii=False, indent=2)
            )

        try:
            from utils import extract_json, retry_llm_call
            response = retry_llm_call(
                lambda: client.chat.completions.create(
                    model=model,
                    max_tokens=1024,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                )
            )
            text = response.choices[0].message.content or ""
            parsed = extract_json(text)
            if parsed:
                self._situation_summary = parsed
                self._compacted_finding_count = len(self._findings)
                self._add_event("compactor", "compacted",
                                f"{len(self._findings)} findings → summary")
                self._save()
        except Exception as exc:
            print(f"[Compact] Summarization failed: {exc}")

    def get_commander_view(self) -> dict:
        """Return a compressed view for the Commander.

        Includes: situation summary, recent findings, recent task history
        (so Commander can see what was tried and what failed), and stats.
        """
        pending = self.get_pending_tasks()
        all_findings = self.get_findings()
        recent_findings = all_findings[-5:]

        # Truncate large data in recent findings for display
        truncated = []
        for f in recent_findings:
            f = dict(f)
            if "data" in f and len(str(f["data"])) > 300:
                data_str = str(f["data"])
                f["data"] = data_str[:300] + (
                    f"... (truncated, {len(data_str)} chars total)"
                )
            truncated.append(f)
        recent_findings = truncated

        # Recent task history — Commander needs to see failures to avoid repeats
        all_tasks = self.get_all_tasks()
        recent_tasks = []
        for t in all_tasks[-10:]:
            task_info = {
                "id": t.get("id", ""),
                "type": t.get("type", ""),
                "status": t.get("status", ""),
                "instruction": t.get("instruction", "")[:120],
            }
            if t.get("output_data"):
                od = t["output_data"]
                task_info["summary"] = str(od.get("summary", ""))[:150]
                if od.get("error_detail"):
                    ed = od["error_detail"]
                    task_info["error"] = (
                        f"{ed.get('error_type', 'unknown')}: "
                        f"{ed.get('detail', '')[:100]}"
                    )
            recent_tasks.append(task_info)

        return {
            "goal": self.get_goal(),
            "situation_summary": self._situation_summary,
            "pending_tasks": pending,
            "recent_tasks": recent_tasks,
            "recent_findings": recent_findings,
            "stats": {
                "total_findings": len(all_findings),
                "flags": len(self.get_findings_by_type("flag")),
                "vulnerabilities": len(
                    self.get_findings_by_type("vulnerability")
                ),
                "assets": len(self.get_findings_by_type("asset")),
                "credentials": len(self.get_findings_by_type("credential")),
            },
            "recent_events": self.get_recent_events(10),
        }
