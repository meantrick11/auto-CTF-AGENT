"""Worker registry — singleton that maps task types to domain workers."""

from dataclasses import dataclass, field

from workers.base_worker import BaseWorker


@dataclass
class WorkerEntry:
    name: str
    domain: str
    task_prefixes: list[str]  # e.g. ["web_"] — matched against task.type
    worker: BaseWorker = field(repr=False)


class WorkerRegistry:
    """Global registry for all domain workers.

    Singleton — same instance everywhere. Workers register with
    task type prefixes; the registry routes tasks to the right worker.

    Usage:
        registry = get_worker_registry()
        registry.register(WebWorker(), name="web_worker",
                          domain="web", task_prefixes=["web_"])
        worker = registry.route("web_recon")  # → WebWorker
    """

    _instance: "WorkerRegistry | None" = None

    def __new__(cls) -> "WorkerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._workers: dict[str, WorkerEntry] = {}
        return cls._instance

    def register(self, worker: BaseWorker, *, name: str,
                 domain: str, task_prefixes: list[str]) -> None:
        entry = WorkerEntry(
            name=name, domain=domain,
            task_prefixes=task_prefixes, worker=worker,
        )
        self._workers[name] = entry

    def route(self, task_type: str) -> BaseWorker | None:
        """Find the first worker whose task_prefixes match task_type."""
        for entry in self._workers.values():
            for prefix in entry.task_prefixes:
                if task_type.startswith(prefix):
                    return entry.worker
        return None

    def get(self, name: str) -> BaseWorker | None:
        entry = self._workers.get(name)
        return entry.worker if entry else None

    def list_all(self) -> list[WorkerEntry]:
        return list(self._workers.values())


def get_worker_registry() -> WorkerRegistry:
    return WorkerRegistry()
