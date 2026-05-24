# CTFAgent — Architecture Spec & Worker Paradigm

## Component Map

```
                    ┌─────────────┐
                    │   Engine    │  sole coupling point — drives the loop
                    └──┬───┬───┬──┘
         ┌─────────────┤   │   ├─────────────┐
         ▼             ▼   │   ▼             ▼
    Commander      Worker  │  Filter      Blackboard
    (decide)       (execute)│ (clean)      (store)
         │             │   │   │             │
         └─────┬───────┘   │   └─────┬───────┘
               │           │         │
          No direct         │   Compactor
          import            │   (summarize)
                            │
                      Hook System (7 events)
```

## 1. Component Contracts

### Commander — "Reads state, decides next actions"
| | |
|---|---|
| **File** | `commander/agent.py` |
| **Input** | `dict` — `get_commander_view()` from Blackboard |
| **Output** | `dict` — `{decision, reasoning, new_tasks[], final_summary}` |
| **LLM** | Yes — single call per round, `response_format={"type": "json_object"}` |
| **Tools** | None |
| **Depends on** | `config`, `utils` |
| **Must NOT** | Import Worker, call tools, execute anything |
| **Contract** | Returns structured dict on error too (never raises) |

### Worker — "Executes one task, returns findings"
| | |
|---|---|
| **Base class** | `workers/base_worker.py::BaseWorker` |
| **Return type** | `TaskResult` (status, summary, output_data, findings, error_detail) |
| **Finding type** | `WorkerFinding` (type, title, data, confidence, source_task_id) |
| **LLM** | Yes — tool-calling loop, max 8 iterations |
| **Tools** | Yes — via `ToolRegistry` |
| **Depends on** | `config`, `utils`, `tools` |
| **Must NOT** | Import Commander, create tasks, decide strategy |
| **Contract** | `execute(task: dict, snapshot: dict) -> TaskResult` |

### Blackboard — "Stores and serves state"
| | |
|---|---|
| **File** | `blackboard/blackboard.py` |
| **Role** | Single source of truth. Findings are append-only. |
| **Persistence** | JSON file, atomic write |
| **Views** | `snapshot()` — full (for Workers); `get_commander_view()` — compressed (for Commander) |
| **Depends on** | `blackboard/schema.py` only |
| **Must NOT** | Import Commander, Worker, or any agent |

### Filter — "Cleans findings without dropping data"
| | |
|---|---|
| **File** | `filter/cleaner.py` |
| **Hook** | `after_execute` |
| **Operations** | Dedup (type+title), normalize, mark large data |
| **LLM** | No — pure rules, zero cost |
| **Rule** | **Never drops findings.** No confidence-based deletion. |

### Compactor — "Summarizes accumulated findings"
| | |
|---|---|
| **Location** | `Blackboard.compact()` method |
| **Trigger** | `_needs_compact()` — findings data > 3000 chars |
| **LLM** | Yes — generates `situation_summary` dict |
| **Rule** | Writes to separate field. Original findings untouched. |
| **Failure** | Non-critical — fails silently, Commander gets larger view |

### Engine — "Drives the loop"
| | |
|---|---|
| **File** | `orchestrator/engine.py` |
| **Role** | Only file that imports both Commander and Worker |
| **Loop** | Commander.plan → create tasks → Worker.execute → Filter → compact → repeat |

### Hook System
| | |
|---|---|
| **File** | `hooks.py` |
| **Events** | before_plan, after_plan, before_task_create, before_execute, after_execute, on_finding, on_complete |
| **Usage** | `@on("event_name")` decorator + `event.block("reason")` |

---

## 2. Information Flow

```
                      Commander (compressed view)
                      ▲
                      │  get_commander_view():
                      │  ├── situation_summary (LLM compacted)
                      │  ├── pending_tasks
                      │  ├── recent_tasks (10, with error_detail)
                      │  ├── recent_findings (5, truncated)
                      │  ├── stats
                      │  └── recent_events (10)
                      │
Worker.execute(task, full_snapshot)  ←── Worker gets ALL findings (needs detail)
                      │
                      ▼
                TaskResult
                      │
                      ├── Filter (after_execute): dedup + normalize + mark
                      │
                      ▼
                Blackboard.add_finding()
                      │
                      ├── Duplicate check: (type, title) match → boost confidence
                      │      + confirmed_by counter
                      │
                      ▼
                complete_task(output_data + error_detail)
                      │
                      ▼
                _maybe_compact()
                      │  threshold: findings data > 3000 chars
                      │  input: all findings + failed tasks
                      │  output: situation_summary dict
                      │
                      ▼
                Next round: Commander sees updated summary + error history
```

### Data format: Finding
```python
{
    "type": "asset|vulnerability|flag|credential|info",
    "title": "human-readable one-liner",
    "data": {...},          # raw evidence, truncated for display if >500 chars
    "confidence": 0.0-1.0,  # boosted on duplicate confirmation
    "confirmed_by": 0,       # how many tasks confirmed this
    "source_task_id": "...",
}
```

### Data format: TaskResult
```python
{
    "status": "completed|failed",
    "summary": "...",
    "output_data": {...},
    "findings": [WorkerFinding, ...],
    "error_detail": {           # only on failure
        "error_type": "network_error|auth_failed|tool_error|...",
        "detail": "human-readable",
        "exception": "ExceptionClassName",
    }
}
```

---

## 3. Worker Paradigm

### 3.1 BaseWorker Contract

Every Worker MUST:
- Extend `BaseWorker` (`workers/base_worker.py`)
- Implement `execute(task: dict, snapshot: dict) -> TaskResult`
- Return `TaskResult` with `error_detail` on failure (structured, not just "failed")
- Define `name` and `domain` class attributes
- NOT import Commander or any other agent

### 3.2 Template: Adding a New Worker

**Step 1 — Create directory structure**
```
workers/<domain>/
├── agent.py
├── prompts/
│   └── system_prompt.txt
└── __init__.py
```

**Step 2 — Implement worker** (`workers/<domain>/agent.py`)
```python
from config import DEEPSEEK_MODEL, create_client
from utils import extract_json, retry_llm_call
from workers.base_worker import BaseWorker, TaskResult, WorkerFinding
from tools.registry import get_registry

class CryptoWorker(BaseWorker):
    name = "crypto_worker"
    domain = "crypto"

    def __init__(self, model=None):
        self.model = model or DEEPSEEK_MODEL
        self._client = create_client(model)
        self.tools = get_registry().get_multi(["crypto", "shared"])
        # Load system prompt from prompts/system_prompt.txt

    def execute(self, task: dict, snapshot: dict) -> TaskResult:
        # 1. Build messages from task + snapshot
        # 2. Call LLM tool-calling loop (max 8)
        # 3. Parse final output → TaskResult.from_dict()
        # 4. On exception → self._build_failure() with structured error_detail
        pass

    def _build_failure(self, task_id, instruction, exc) -> TaskResult:
        # Classify error type and return structured TaskResult
        pass
```

**Step 3 — Write system prompt** (`workers/<domain>/prompts/system_prompt.txt`)
- Persona: what this worker is, what it can do
- Authority: tools it can use, what it CANNOT do
- Output format: CRITICAL — "Output ONLY JSON, no other text"
- Finding types relevant to this domain

**Step 4 — Create domain tools** (`tools/<domain>/`)
```python
from tools.registry import register_tool

@register_tool(category="crypto", description="Decrypt AES-CBC ciphertext")
def aes_decrypt(ciphertext: str, key: str, iv: str) -> dict:
    ...
```

**Step 5 — Import tools** in `tools/__init__.py`:
```python
import tools.crypto.decrypt  # @register_tool fires on import
```

**Step 6 — Register worker** in `orchestrator/engine.py::__init__()`:
```python
from workers.crypto.agent import CryptoWorker
reg.register(CryptoWorker(model=model), name="crypto_worker",
             domain="crypto", task_prefixes=["crypto_"])
```

**Step 7 — Export** in `workers/__init__.py`

**Step 8 — Commander needs ZERO changes** — task_prefixes handle routing.

### 3.3 Worker System Prompt Rules

- **CRITICAL: Output ONLY the JSON object.** No markdown, no text before/after.
- Worker CAN call tools repeatedly to investigate
- Worker CANNOT create tasks or decide overall strategy
- Worker MUST report findings with appropriate confidence levels
- On failure: explain what went wrong specifically (not "it failed")

---

## 4. Architecture Rules

### Module Independence
- Commander ⇎ Worker: zero imports of each other. Communication only via Blackboard.
- Engine is the sole coupling point.
- Blackboard depends on nothing outside its own schema.
- Tools are pure functions with type hints. No state, no LLM calls.

### Finding Lifecycle
1. Worker creates `WorkerFinding` (no id/timestamp)
2. Filter deduplicates within task output
3. Engine converts to dict → `Blackboard.add_finding()`
4. Blackboard assigns id + timestamp → `Finding` dataclass
5. Cross-task duplicate check → confidence boost if matching (type, title)
6. Findings are **append-only** — never modified after creation (except confidence boost)

### LLM Call Points (only 3 in system)
| Caller | Purpose | Retry |
|---|---|---|
| Commander | Decide next actions (1 call/round) | Yes |
| Worker | Tool-calling loop (≤8 calls/task) | Yes |
| Compactor | Summarize findings (threshold-triggered) | No (non-critical) |

### Context Budget
- Commander: summary + 5 recent findings + 10 recent tasks + stats + 10 events
- Worker: full snapshot (all findings, all tasks — Worker needs detail)
- Compaction threshold: >3000 chars of findings data

### Error Handling
- Commander.plan() and Worker.execute(): never raise, return structured result
- Worker failure: `TaskResult(status="failed")` with `error_detail`
- Compactor failure: logged, execution continues
- Hook exceptions: caught and logged, event continues

### What NOT to do
- Don't add modules that do more than one thing
- Don't let Commander and Worker import each other
- Don't truncate findings by deleting data (mark, don't drop)
- Don't add LLM call points without retry (except Compactor)
- Don't modify findings after they're written to Blackboard
