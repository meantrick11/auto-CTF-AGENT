from workers.base_worker import BaseWorker, TaskResult, WorkerFinding
from workers.registry import WorkerRegistry, WorkerEntry, get_worker_registry
from workers.web.agent import WebWorker

__all__ = [
    "BaseWorker", "TaskResult", "WorkerFinding",
    "WorkerRegistry", "WorkerEntry", "get_worker_registry",
    "WebWorker",
]
