"""Base worker interface — all domain workers extend this."""

from abc import ABC, abstractmethod

from tools.registry import ToolDef
from blackboard.schema import TaskResult, WorkerFinding  # noqa: F401 — re-export


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
