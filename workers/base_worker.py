"""Base worker interface — all domain workers extend this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from tools.registry import ToolDef


@dataclass
class WorkerFinding:
    """Standard finding produced by a Worker. Engine enriches it into a blackboard Finding."""

    type: str  # "asset" | "vulnerability" | "flag" | "credential" | "info"
    title: str
    data: dict = field(default_factory=dict)
    confidence: float = 1.0
    source_task_id: str = ""


@dataclass
class TaskResult:
    """Standard return type for ALL Worker.execute() calls.

    Every Worker MUST return a TaskResult (or a plain dict — see note below).
    This is the contract between Action Plane and the rest of the system.
    Filter, Blackboard, and Engine all depend on this shape.
    """

    status: str  # "completed" | "failed"
    summary: str = ""
    output_data: dict = field(default_factory=dict)
    findings: list[WorkerFinding] = field(default_factory=list)

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
        )


class BaseWorker(ABC):
    """Abstract base for domain-specialized workers.

    Each worker operates in a specific domain (web, crypto, etc.),
    has access to a set of tools, and executes tasks from the blackboard.
    """

    name: str
    domain: str
    tools: list[ToolDef]

    @abstractmethod
    def execute(self, task: dict, blackboard_snapshot: dict) -> TaskResult:
        """Execute a task and return a TaskResult with findings.

        Args:
            task: Task dict from blackboard with keys:
                  id, type, instruction, input_data
            blackboard_snapshot: Current blackboard state for context
                                 (goal, all findings so far, etc.)

        Returns:
            TaskResult with status, summary, output_data, and findings.
        """
        ...
