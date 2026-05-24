# Filter — Data Washer

## Role

Rule-based data cleaner between Worker output and Blackboard. Hooks into `after_execute`. **Does one thing: clean findings without dropping data.**

## Status: Implemented (2026-05-24)

## Hook Point

**`after_execute`** — fires after `Worker.execute()` returns, before findings are written to blackboard.

```
Worker.execute() → TaskResult
                         │
                    ┌────▼────┐
                    │  Filter  │  ← after_execute hook
                    └────┬────┘
                         │
                    cleaned TaskResult
                         │
                    ┌────▼────┐
                    │ Blackboard.write()
                    └─────────┘
```

## What Filter Does

| Operation | How | Safe? |
|---|---|---|
| **Dedup** | Same (type, title) → merge, take higher confidence, merge data dicts | Yes — no data lost |
| **Normalize** | Fill missing `type` → "info", `title` → "untitled" | Yes |
| **Truncate mark** | data > 500 chars → set `_truncated=True`, `_original_size=N` | Yes — original data intact |

## What Filter Does NOT Do

- **Does NOT drop low-confidence findings** — that's the Compactor's job (LLM judgment)
- **Does NOT delete data** — only merges and marks
- **Does NOT call LLM** — pure rules, zero cost

## Files

| File | Role |
|---|---|
| `cleaner.py` | Filter hook implementation — `@on("after_execute")` |
| `__init__.py` | Imports cleaner to register hook |
| `README.md` | This file |

## Principle

Filter is a **mechanical worker**, not an intelligence analyst. It does safe, cheap, deterministic operations. Judgment calls (what's important, what's noise) belong to the Compactor, which is LLM-powered and runs separately.
