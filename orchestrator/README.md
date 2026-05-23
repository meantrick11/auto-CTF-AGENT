# Orchestrator — Engine

## Role

The main event loop that wires all components together. It owns the blackboard lifecycle, drives the Commander-Worker loop, and decides when execution terminates.

## Files

| File | Role | Input | Output |
|---|---|---|---|
| `engine.py` | Main loop: init → Commander.plan → Worker.execute → converge → repeat | User goal string + config | Final report |

## Loop Logic (Pseudocode)

```
1. blackboard.create_goal(user_input)
2. for round in 1..max_rounds:
   a. snapshot = blackboard.snapshot()
   b. [hook: before_plan] → guardrail check
   c. decision = commander.plan(snapshot)
   d. [hook: after_plan]
   e. if decision is "completed" or "failed": break
   f. for each new_task in decision.new_tasks:
        [hook: before_task_create] → guardrail check
        blackboard.create_task(...)
   g. for each pending task:
        route via WorkerRegistry.route(task_type)
        [hook: before_execute] → last safety gate
        worker.execute(task) → TaskResult
        [hook: after_execute] → Filter cleans/deduplicates
        for each finding: [hook: on_finding] → blackboard.add_finding()
        blackboard.complete_task(...)
3. [hook: on_complete] → print final summary
```

## Worker Routing

Uses `WorkerRegistry` (singleton, same pattern as ToolRegistry). Each worker registers with `task_prefixes` (e.g. `["web_"]`). `_route_task()` calls `registry.route(task_type)` with fallback to `web_worker`. No hardcoded if/elif chains — adding a worker is one `reg.register()` call.

## Result Handling

Engine normalizes both `TaskResult` and plain dicts in `_execute_task()`. Worker's `execute()` MUST return `TaskResult`. The Filter hook (`after_execute`) receives the raw object and can modify in place.

## Configuration

- `max_rounds`: int = 10 — safety limit to prevent infinite loops
- `model`: str = "deepseek-v4-pro" — LLM model for agents

## Input

- User's natural language goal (e.g., "攻破 http://target.com 获取flag")

## Output

- Console log of each round's actions
- Final report: goal status, all findings, key decisions
