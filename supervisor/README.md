# Supervisor Module — Immune System Agent

Third agent in the three-agent architecture. Monitors Commander and Worker, intervenes when things go wrong.

## Role

```
Commander  → 战术大脑（决定做什么）
Worker     → 执行肌肉（做）
Supervisor → 免疫系统（盯着前两个，确保不出事）
```

## Architecture: Two-Layer

```
Hook 触发 → Layer 1 规则 → 通过 → 放行
                         → 可疑 → Layer 2 Agent (LLM) 语义判断
                         → 危险 → 直接 block
```

- **Layer 1 (rules)**: Safety checks, drift detection, repetition detection, dedup, compaction triggering. Pure Python, zero LLM cost, runs on every hook.
- **Layer 2 (agent)**: Semantic judgment via LLM. Called ONLY when Layer 1 flags something as "suspicious". At most 1-2 calls per round.

## Files

| File | Layer | Role |
|---|---|---|
| `__init__.py` | Both | Registers all 7 hooks, wires Layer 1 → Layer 2 escalation |
| `safety.py` | Layer 1 | Task/instruction safety (formerly `guardrail/`) |
| `quality.py` | Layer 1 | Finding dedup/normalize/validate (formerly `filter/`) |
| `drift.py` | Layer 1 | Stagnation/repetition/stuck detection (formerly `evaluator/`) |
| `maintenance.py` | Layer 1 | Compaction triggering, observer notes |
| `agent.py` | Layer 2 | SupervisorAgent — LLM-based semantic review |
| `prompts/system_prompt.txt` | Layer 2 | Supervisor Agent system prompt |

## Hook Coverage

| Hook | What Supervisor Does |
|---|---|
| `before_plan` | Check blackboard sanity, stagnation detection |
| `after_plan` | Validate Commander decision — hallucinations? loops? |
| `before_task_create` | Task safety + repetition detection |
| `before_execute` | Last safety gate |
| `after_execute` | Finding quality, worker stuck detection, failure tracking |
| `on_finding` | Finding type/confidence validation |
| `on_complete` | Reset state, write final summary |

## Observer Notes

Supervisor writes `observer_notes` to Blackboard. Commander sees them in every round's view. Notes have:
- `category`: safety, drift, quality, strategy
- `severity`: info, warn, block
- `message`: concise, actionable

## Redirection System (Active Intervention)

Stronger than observer_notes — actively constrains Commander/Worker behavior:

| Mechanism | What It Does |
|---|---|
| `set_redirection(blocked_types, suggested, reason)` | Blocks specific task types from being created |
| `clear_redirection()` | Lifts the block when a task succeeds with substantial findings |
| `_is_blocked_by_redirection(task_def)` | Checked in `before_task_create` — blocks dead-end tasks |
| `_analyze_and_intervene(result, task, snapshot)` | Reads Worker tool_trace, detects stuck (>=5 same-tool errors or >=70% error rate), escalates to Layer 2 Agent |

### Intervention Escalation Path:
```
1. write_note(warn) → Commander sees it, may or may not listen
2. write_note(block) → before_task_create enforces it
3. set_redirection() → before_task_create BLOCKS dead-end task types
```

