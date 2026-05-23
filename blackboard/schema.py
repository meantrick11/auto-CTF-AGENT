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
