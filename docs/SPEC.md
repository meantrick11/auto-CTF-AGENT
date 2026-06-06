# CTFAgent — Architecture Spec (v2)

## Component Map

```
                          ┌──────────────┐
                          │   Monitor    │  横切度量（只读不写）
                          │ tokens/耗时   │  Hook: before_plan, on_complete
                          └──────────────┘

User Goal
    │
    ▼
┌──────────┐  方向分配     ┌──────────────┐
│ Commander │────────────→ │    Engine    │  sole coupling point
│ 读状态    │              │  驱动循环     │
│ 定方向    │←─────────────│  并行调度     │
└──────────┘  读压缩视图   └──────────────┘
                               │        ↑
                               │分发    │写 findings
                               ▼        │
                         ┌──────────┐   │
                         │ Worker×N │   │  同域多实例
                         │ 执行任务  │───┘  不同攻击方向
                         └──────────┘
                               │
                               ▼ Worker 输出
                    ┌─────────────────────┐
                    │   Context Manager   │  信息质量控制
                    │  Phase 1: Filter    │  规则, 免费
                    │  Phase 2: Compact   │  LLM, 阈值触发
                    └─────────────────────┘
                               │
                               ▼ 干净数据 + 摘要
                    ┌─────────────────────┐
                    │     Blackboard      │  信息交换 + 短期记忆
                    │                     │  只存当前运行状态
                    └─────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            ┌──────────────┐    ┌──────────────────┐
            │  Evaluator   │    │     Memory       │
            │  方向纠偏     │    │   跨运行持久知识   │
            │  写提醒notes  │    │   待实现(RAG)     │
            └──────────────┘    └──────────────────┘
                    │
                    ▼ Blackboard (observer_notes)
              Commander 下轮读到
```

---

## 1. Module Contracts — "Each module does ONE thing"

### Blackboard — "信息交换 + 短期记忆"
| | |
|---|---|
| **File** | `blackboard/blackboard.py` |
| **Schema** | `blackboard/schema.py` — all system data types |
| **Role** | Single source of truth for the current run. Stores and serves state. |
| **Persistence** | JSON file, atomic write. Cleared between runs. |
| **Views** | `snapshot()` — full (for Workers); `get_commander_view()` — compressed (for Commander) |
| **Depends on** | `blackboard/schema.py` only |
| **Must NOT** | Compress data, make quality judgments, call LLM, import any agent |
| **Key rule** | Findings are append-only. Compaction writes to separate summary field. |

### Commander — "读状态，定方向，分配 Worker"
| | |
|---|---|
| **File** | `commander/agent.py` |
| **Input** | `CommanderView` — compressed: summary + recent findings + observer_notes + stats |
| **Output** | `Decision` dataclass — validated (decision, reasoning, directions[], final_summary) |
| **LLM** | Yes — single call per round, `response_format={"type": "json_object"}` |
| **Tools** | None |
| **Depends on** | `config`, `utils`, `blackboard.schema` |
| **Must NOT** | Execute tools, talk to Workers directly, import Worker |
| **New in v2** | Allocates **directions** (not individual tasks). Each direction = one Worker instance. Can output "hold" to skip a round. |

### Worker — "接收一个方向，执行一组任务"
| | |
|---|---|
| **Base class** | `workers/base_worker.py::BaseWorker` |
| **Return type** | `TaskResult` (enforced — no dict fallback) |
| **LLM** | Yes — tool-calling loop, max 8 iterations |
| **Tools** | Yes — via `ToolRegistry` |
| **Depends on** | `config`, `utils`, `tools`, `blackboard.schema` |
| **Must NOT** | Import Commander, decide strategy, talk to other Workers |
| **New in v2** | Multiple instances of the same domain Worker run in parallel, each with a different attack direction. Worker is stateless — all state lives on Blackboard. |

### Engine — "驱动循环，按方向并行分发"
| | |
|---|---|
| **File** | `orchestrator/engine.py` |
| **Role** | Only file that imports both Commander and Worker. Sole coupling point. |
| **Loop** | Commander.plan → launch Workers per direction → Context Manager → Evaluator → repeat |
| **New in v2** | Groups tasks by direction. Same-direction tasks run serial. Different directions run parallel. Max workers configurable. |

### Context Manager — "信息质量控制"
| | |
|---|---|
| **Location** | `context/` module (new) |
| **Phase 1 — Filter** | Rule-based. Dedup (type+title), normalize, mark large data. **Never drops findings.** |
| **Phase 2 — Compact** | LLM-based. Threshold-triggered (>3000 chars). Generates structured summary with explicit PRESERVE/DISCARD rules. |
| **LLM** | Only Phase 2 |
| **Hook** | `after_execute` |
| **Output** | Cleaned findings + situation_summary → Blackboard |

### Evaluator — "策略评估 + 方向纠偏"
| | |
|---|---|
| **Location** | `evaluator/` module (new) |
| **Role** | Reads recent N rounds of execution traces. Detects drift, repeated failures, stale directions. Writes observer_notes to Blackboard for Commander. |
| **LLM** | Optional — primarily rule-based. Can call LLM for complex judgment. |
| **Hook** | New hook: `after_round` |
| **Output** | `observer_notes` — reminders and suggestions → Blackboard |
| **Must NOT** | Execute tasks, modify findings, make Commander decisions |

### Monitor — "横切度量"
| | |
|---|---|
| **Location** | `monitor/` module (new) |
| **Role** | Pure observer — reads only, never writes to Blackboard. Tracks token usage, round timing, success/failure ratios, direction distribution. |
| **LLM** | No |
| **Hooks** | `before_plan`, `after_execute`, `on_complete` |
| **Output** | Final report statistics section |

### Memory — "跨运行持久知识"
| | |
|---|---|
| **Location** | `memory/` module (future) |
| **Role** | Stores confirmed findings across runs. RAG-retrievable. Not active in current session — purely for future runs. |
| **Status** | Deferred — not in v2 MVP |

---

## 2. Information Flow

```
Round N:
  Commander reads CommanderView {
      situation_summary    ← Context Manager Phase 2 产出
      recent_findings      ← Context Manager Phase 1 清洗后
      observer_notes       ← Evaluator 上轮产出
      stats, tasks, events
  }
  Commander outputs Decision {
      decision: "continue" | "hold" | "completed" | "failed"
      directions: [
          {name: "sqli", tasks: [...], handoff: "..."},
          {name: "xss",  tasks: [...], handoff: "..."},
      ]
  }
      │
      ▼
  Engine launches Workers parallel by direction:
      Worker#1.execute(direction="sqli", tasks=[...])
      Worker#2.execute(direction="xss",  tasks=[...])
      │
      ▼ Worker outputs TaskResult (findings mostly "suspected")
      │
      ├── Context Manager Phase 1 (Filter):
      │       dedup + normalize + mark
      │
      ├── Context Manager Phase 2 (Compact):
      │       阈值触发 → LLM 结构化摘要
      │
      ▼ 写入 Blackboard
      │
      ├── Evaluator (after_round):
      │       读最近 N 轮轨迹
      │       检测: 重复试错 / 方向偏移 / 停滞
      │       写 observer_notes → Blackboard
      │
      ▼
Round N+1: Commander 看到 observer_notes + 新数据, 继续或纠偏
```

---

## 3. Data Types (all in `blackboard/schema.py`)

### Finding — 加 status 语义区分
```python
{
    "type": "asset|vulnerability|flag|credential|info",
    "title": "human-readable one-liner",
    "data": {...},
    "confidence": 0.0-1.0,
    "status": "suspected|confirmed|dead_end",  # NEW
    "source_task_id": "...",
    "direction": "sqli",  # NEW — which attack direction
}
```

- `suspected` — Worker 产出的初始猜测
- `confirmed` — 重复验证或跨任务确认
- `dead_end` — 多次尝试无果，Evaluator 标记

### Decision — Commander 输出（已实现）
```python
@dataclass
class Decision:
    decision: str           # "continue" | "hold" | "completed" | "failed"
    reasoning: str
    directions: list[dict]  # NEW — [{name, tasks, handoff}, ...]
    final_summary: str
```

### TaskResult — Worker 合约（已实现，已迁至 schema.py）
### WorkerFinding — Worker 产出（已实现，已迁至 schema.py）

---

## 4. Architecture Rules

### Module Independence
- Commander ⇎ Worker: zero imports. Communication only via Blackboard.
- Engine is the sole coupling point.
- Context Manager, Evaluator, Monitor: each independent, hook into Engine events.
- Blackboard depends on nothing outside its own schema.
- Tools are pure functions. No state, no LLM calls.

### Finding Lifecycle (v2)
1. Worker creates `WorkerFinding` (status defaults to `suspected`)
2. Context Manager Phase 1 (Filter): dedup + normalize
3. Engine writes to Blackboard → `Finding` dataclass (id + timestamp added)
4. Cross-task duplicate → confidence boost, status upgraded to `confirmed`
5. Evaluator detects repeated failures → status marked `dead_end`
6. Findings are **append-only** — modified only via confidence boost and status transitions

### LLM Call Points (v2)
| Caller | Purpose | Retry | Cost |
|---|---|---|---|
| Commander | Decide directions (1 call/round) | Yes | 付费 |
| Worker | Tool-calling loop (≤8 calls/task) | Yes | 付费 |
| Context Manager Phase 2 | Summarize findings (threshold) | Yes | 付费 |
| Evaluator | Complex drift judgment (optional) | No | 按需 |

### Context Budget
- Commander: summary + 5 recent findings + observer_notes + stats + events
- Worker: full snapshot (needs detail to execute)
- Compaction threshold: >3000 chars findings data

### Error Handling
- Commander.plan() and Worker.execute(): never raise, return structured result
- Worker failure: `TaskResult(status="failed")` with `error_detail`
- Compactor failure: logged, execution continues
- Evaluator failure: logged, execution continues (non-critical)
- Hook exceptions: caught and logged

### What NOT to do
- Don't let modules do more than one thing
- Don't let Commander and Worker import each other
- Don't drop findings — mark status instead
- Don't add LLM calls without retry (except Evaluator optional calls)
- Don't modify findings after Blackboard write (except status transitions)
