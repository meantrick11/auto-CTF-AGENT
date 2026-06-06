# Commander — Orchestration Plane

## Role

The tactical brain. **Does one thing: reads state and decides next actions.** Commander reads a compressed blackboard view, reasons about the situation, and generates subtasks. It does NOT execute any security tools.

## Files

| File | Role |
|---|---|
| `agent.py` | Commander: takes commander_view, returns plan decision |
| `prompts/system_prompt.txt` | System prompt defining persona and constraints |

## Input Protocol

Commander receives `get_commander_view()` from the blackboard — a compressed view designed to fit in context:

```python
{
    "goal": {"id": "...", "description": "...", "status": "running"},
    "situation_summary": {              # LLM-compacted (may be None before first compaction)
        "summary": "one paragraph overview",
        "flags": [...],
        "vulnerabilities": [...],
        "assets": [...],
        "credentials": [...],
        "key_observations": [...],
        "recommended_steps": [...]
    },
    "pending_tasks": [...],             # only pending tasks
    "recent_findings": [...],           # last 5, data truncated to 300 chars
    "stats": {                          # summary counts
        "total_findings": N,
        "flags": N, "vulnerabilities": N,
        "assets": N, "credentials": N
    },
    "recent_events": [...]              # last 10
}
```

## Output Protocol

Commander returns a `Decision` dataclass (defined in `blackboard/schema.py`). Engine accesses typed attributes — no `.get()` fallbacks.

```python
@dataclass
class Decision:
    decision: str          # "continue" | "completed" | "failed"
    reasoning: str = ""
    new_tasks: list[dict]  # [{type, instruction, input_data}, ...]
    final_summary: str = ""
```

`Decision.from_llm_output(dict)` validates that `decision` is exactly one of the three allowed values. A typo like `"complete"` raises `ValueError` instead of being silently ignored. `Decision.failed(reason)` is the convenience factory for error states.

## Commander's Authority

- **CAN**: Read blackboard (compressed view), create tasks, update goal status
- **CANNOT**: Call security tools, execute commands, talk to workers directly
- **MUST delegate**: Even trivial operations must be tasks for workers
