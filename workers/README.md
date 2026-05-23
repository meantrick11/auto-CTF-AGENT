# Workers — Action Plane

## Role

Domain-specialized execution agents. Each Worker claims tasks from the blackboard, invokes the appropriate tools, extracts key findings, and writes results back.

## Design

All Workers extend `BaseWorker` which defines the standard interface + enforced return schema. Workers are stateless — all state lives on the blackboard.

## Files

| File | Role | Input | Output |
|---|---|---|---|
| `base_worker.py` | Abstract base + **TaskResult** + **WorkerFinding** dataclasses | — | — |
| `registry.py` | Singleton WorkerRegistry. Prefix-based routing. Same pattern as ToolRegistry. | — | — |
| `web/agent.py` | Web security specialist Worker | Task dict + blackboard snapshot | **TaskResult** |
| `web/prompts/system_prompt.txt` | Web Worker persona and tool-use instructions | — | — |

## BaseWorker Interface

```python
class BaseWorker(ABC):
    name: str              # "web_worker"
    domain: str            # "web"
    tools: list[ToolDef]   # Available tools from registry

    @abstractmethod
    def execute(self, task: dict, blackboard_snapshot: dict) -> TaskResult:
        """Claim a task, execute it, return structured result."""
```

## TaskResult — The Worker Contract

ALL `Worker.execute()` methods MUST return a `TaskResult`. This is the Action Plane schema contract. Filter, Blackboard, and Engine all depend on this shape.

```python
@dataclass
class TaskResult:
    status: str              # "completed" | "failed"
    summary: str             # Human-readable summary
    output_data: dict        # Raw tool output (gets written to task.output_data)
    findings: list[WorkerFinding]  # Extracted intelligence

@dataclass
class WorkerFinding:
    type: str               # "asset" | "vulnerability" | "flag" | "credential" | "info"
    title: str
    data: dict
    confidence: float       # 0.0–1.0
    source_task_id: str
```

`TaskResult.from_dict(d)` bridges raw LLM JSON → structured object. Engine normalizes both TaskResult and plain dicts (backward compat for hook modifications).

## WorkerRegistry — Registration & Routing

```python
from workers.registry import get_worker_registry

reg = get_worker_registry()
reg.register(WebWorker(model), name="web_worker",
             domain="web", task_prefixes=["web_"])

# Routing: task_type → Worker
worker = reg.route("web_recon")     # → WebWorker (matches "web_" prefix)
worker = reg.route("web_exploit")   # → WebWorker
worker = reg.route("crypto_aes")    # → None (no matching prefix, falls back to web_worker)
```

Singleton pattern — same instance everywhere. Registration happens once in `engine.__init__()`.

## Adding a New Domain Worker

1. Create `workers/<domain>/agent.py` — extend BaseWorker, implement `execute() → TaskResult`
2. Create `workers/<domain>/prompts/system_prompt.txt`
3. Register tools under `tools/<domain>/` using `@register_tool`
4. In `orchestrator/engine.py` `__init__`: add `reg.register(..., task_prefixes=["<domain>_"])`
5. In `workers/__init__.py`: add the Worker class export
6. Commander needs NO changes (it generates task types by convention — the prefix does the routing)

## Current Workers (MVP)

| Worker | Domain | Task Prefixes | Tools |
|---|---|---|---|
| WebWorker | Web Security | `web_` | shared (encoding, network) + web (recon, exploit) |
