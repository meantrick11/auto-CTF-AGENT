from workers.base_worker import BaseWorker
from workers.registry import WorkerRegistry, WorkerEntry, get_worker_registry
from workers.web.agent import WebWorker
from blackboard.schema import TaskResult, WorkerFinding  # re-export from canonical location

__all__ = [
    "BaseWorker", "TaskResult", "WorkerFinding",
    "WorkerRegistry", "WorkerEntry", "get_worker_registry",
    "WebWorker",
]
