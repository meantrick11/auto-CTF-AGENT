# Orchestrator — Engine

## Role

The main event loop that wires all components together. **Does one thing: drives the loop.** Owns the blackboard lifecycle, triggers compaction, and decides when execution terminates.

## Files

| File | Role |
|---|---|
| `engine.py` | Main loop: init → Commander.plan → Worker.execute → compact → repeat |

## Loop Logic

```
1. blackboard.create_goal(user_input)
2. for round in 1..max_rounds:
   a. [hook: before_plan]
   b. commander_view = blackboard.get_commander_view()   ← compressed view
   c. decision = commander.plan(commander_view)          ← returns Decision dataclass
   d. [hook: after_plan]
   e. if decision.decision is "completed" or "failed": break
   f. for each new_task:
        [hook: before_task_create]
        blackboard.create_task(...)
   g. for each pending task:
        route via WorkerRegistry.route(task_type)
        [hook: before_execute]
        worker.execute(task, full_snapshot)   ← Worker gets full snapshot
        [hook: after_execute] → Filter cleans (dedup, normalize)
        for each finding: [hook: on_finding] → blackboard.add_finding()
        blackboard.complete_task(...)
   h. _maybe_compact()   ← check threshold, LLM summarize if exceeded
3. [hook: on_complete]
```

## Key Design Points

### Two Views
- **Commander** gets `get_commander_view()` — compressed: situation_summary + recent_findings(5) + stats
- **Worker** gets `snapshot()` — full: all findings (Worker needs detail to do its job)

### Compaction
- Triggered after all tasks in a round are done, before next Commander.plan()
- Threshold: findings data total > 3000 chars
- LLM generates structured summary, stored separately (original findings untouched)

### TaskResult Enforcement
Engine requires `Worker.execute()` to return `TaskResult` (no dict fallback). If a Worker violates this contract, attribute errors surface immediately rather than being silently swallowed.

### Worker Routing
Uses `WorkerRegistry` (singleton). Each worker registers with `task_prefixes` (e.g. `["web_"]`). `_route_task()` calls `registry.route(task_type)` with fallback to `web_worker`. No hardcoded if/elif chains.

## Input

- User's natural language goal (e.g., "Attack http://target.com and capture the flag")

## Output

- Console log of each round's actions
- Final report: outcome, rounds, flag, findings, task history, event log
