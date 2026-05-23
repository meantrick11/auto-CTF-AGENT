# Commander — Orchestration Plane

## Role

The tactical brain. Commander reads the blackboard snapshot, reasons about the current situation, and generates the next set of subtasks. **It does not execute any security tools.** It only reads state and publishes tasks.

## Files

| File | Role | Input | Output |
|---|---|---|---|
| `agent.py` | Commander core: takes blackboard snapshot, returns plan decision | `dict` (blackboard snapshot) | `dict` (decision + new_tasks) |
| `prompts/system_prompt.txt` | System prompt defining Commander's persona and constraints | — | — |

## Input Protocol

```python
# Commander.plan(snapshot) receives:
{
    "goal": {"id": "...", "description": "攻破...", "status": "running"},
    "tasks": [
        {"id": "...", "type": "web_recon", "status": "completed",
         "instruction": "...", "output_data": {...}}
    ],
    "findings": [
        {"id": "...", "type": "asset", "title": "/admin 后台", "data": {...}}
    ],
    "recent_events": [...]
}
```

## Output Protocol

```python
# Commander.plan() returns:
{
    "decision": "continue",       # continue | completed | failed
    "reasoning": "发现新资产 /admin，需要进一步探测",
    "new_tasks": [
        {
            "type": "web_exploit",
            "instruction": "对 /admin 登录口尝试SQL注入",
            "input_data": {"url": "http://target.com/admin", "method": "POST"}
        }
    ],
    "final_summary": ""           # filled when decision is completed/failed
}
```

## Commander's Authority

- **CAN**: Read blackboard, create tasks, update goal status, add events
- **CANNOT**: Call security tools, execute commands, talk to workers directly

## System Prompt Principles

1. You are a CTF tactical commander — plan, don't execute
2. Analyze current findings before deciding next steps
3. Generate 1-3 focused subtasks per round, no more
4. When a flag is found or all attack surfaces are exhausted, declare completion
5. Write tasks with clear, actionable natural language instructions for workers
