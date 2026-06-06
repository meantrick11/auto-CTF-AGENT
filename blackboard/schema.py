"""Data models for the shared blackboard."""

from dataclasses import dataclass, field
from enum import Enum
import uuid
from datetime import datetime, timezone


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingType(str, Enum):
    VULNERABILITY = "vulnerability"
    CREDENTIAL = "credential"
    FLAG = "flag"
    ASSET = "asset"
    INFO = "info"


@dataclass
class Goal:
    description: str
    id: str = field(default_factory=_new_id)
    status: GoalStatus = GoalStatus.PENDING
    created_at: str = field(default_factory=_now)


@dataclass
class Task:
    type: str
    instruction: str
    input_data: dict = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    goal_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: str = ""
    output_data: dict | None = None
    created_at: str = field(default_factory=_now)
    completed_at: str = ""


@dataclass
class Finding:
    type: FindingType
    title: str
    data: dict = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    source_task_id: str = ""
    confidence: float = 1.0
    timestamp: str = field(default_factory=_now)


@dataclass
class EventLog:
    agent_name: str
    action: str
    detail: str = ""
    timestamp: str = field(default_factory=_now)


@dataclass
class Decision:
    """Commander's tactical decision — the contract between Commander and Engine.

    Allowed values for decision: "continue" | "completed" | "failed"
    """

    decision: str  # "continue" | "completed" | "failed"
    reasoning: str = ""
    new_tasks: list[dict] = field(default_factory=list)
    final_summary: str = ""

    @staticmethod
    def from_llm_output(d: dict) -> "Decision":
        """Parse Commander LLM output with validation.

        Validates that 'decision' is present and has a known value.
        Raises ValueError on invalid input so Engine can retry Commander
        instead of silently proceeding with bad data.
        """
        raw = d.get("decision", "")
        if raw not in ("continue", "completed", "failed"):
            raise ValueError(
                f"Commander output has invalid decision: {raw!r}. "
                f"Expected: continue | completed | failed. "
                f"Raw keys: {list(d.keys())}"
            )
        return Decision(
            decision=raw,
            reasoning=d.get("reasoning", ""),
            new_tasks=d.get("new_tasks", []),
            final_summary=d.get("final_summary", ""),
        )

    @staticmethod
    def failed(reason: str) -> "Decision":
        """Convenience: create a failed decision (e.g. on parse error)."""
        return Decision(
            decision="failed",
            reasoning=reason,
            new_tasks=[],
            final_summary="",
        )


@dataclass
class WorkerFinding:
    """Finding produced by a Worker. Engine enriches it into a blackboard Finding."""

    type: str  # "asset" | "vulnerability" | "flag" | "credential" | "info"
    title: str
    data: dict = field(default_factory=dict)
    confidence: float = 1.0
    source_task_id: str = ""


@dataclass
class TaskResult:
    """Standard return type for ALL Worker.execute() calls.

    This is the contract between Action Plane and Engine.
    Filter, Blackboard, and Engine all depend on this shape.
    """

    status: str  # "completed" | "failed"
    summary: str = ""
    output_data: dict = field(default_factory=dict)
    findings: list[WorkerFinding] = field(default_factory=list)
    error_detail: dict | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "summary": self.summary,
            "output_data": self.output_data,
            "findings": [
                {
                    "type": f.type,
                    "title": f.title,
                    "data": f.data,
                    "confidence": f.confidence,
                    "source_task_id": f.source_task_id,
                }
                for f in self.findings
            ],
            "error_detail": self.error_detail,
        }

    @staticmethod
    def from_dict(d: dict) -> "TaskResult":
        findings = [
            WorkerFinding(
                type=f.get("type", "info"),
                title=f.get("title", ""),
                data=f.get("data", {}),
                confidence=f.get("confidence", 1.0),
                source_task_id=f.get("source_task_id", ""),
            )
            for f in d.get("findings", [])
        ]
        return TaskResult(
            status=d.get("status", "failed"),
            summary=d.get("summary", ""),
            output_data=d.get("output_data", {}),
            findings=findings,
            error_detail=d.get("error_detail"),
        )
