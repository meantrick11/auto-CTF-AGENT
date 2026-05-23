# Filter — Data Washer

## Role

Middleware between Worker output and Blackboard. Receives raw Worker execution results, cleans and normalizes them, then passes structured intelligence to the blackboard. Prevents context overload for the Commander.

## Hook Point

**`after_execute`** — fires after `Worker.execute()` returns, before findings are written to blackboard.

```
Worker.execute() → result dict
                         │
                    ┌────▼────┐
                    │  Filter  │  ← after_execute hook
                    └────┬────┘
                         │
                    cleaned result
                         │
                    ┌────▼────┐
                    │ Blackboard.write()
                    └─────────┘
```

## Input (event.data)

```python
{
    "task": {
        "id": "task-001",
        "type": "web_recon",
        "instruction": "...",
        "input_data": {...}
    },
    "result": {
        "status": "completed",
        "summary": "...",
        "output_data": {...},
        "findings": [
            {"type": "asset", "title": "...", "confidence": 1.0, ...},
            {"type": "asset", "title": "...", "confidence": 0.3, ...},  # duplicate
        ]
    }
}
```

## Output (modify event.data["result"] in place)

Filter modifies `event.data["result"]` directly. The engine reads it back after the hook:

```python
# engine.py after firing hook:
ev = fire("after_execute", task=task, result=result)
result = ev.data.get("result", result)  # uses modified version
```

## What Filter Should Do

| Operation | Description | Priority |
|---|---|---|
| **Deduplicate** | Merge findings with same title + same data (e.g., two workers found the same /admin) | High |
| **Confidence filter** | Drop findings with confidence < threshold (default 0.5) | High |
| **Truncate** | Limit verbose output_data to N characters to keep blackboard compact | Medium |
| **Normalize** | Ensure all findings have required fields (type, title, data, confidence) | Medium |
| **Merge assets** | If two assets are sub-paths of the same host, group them | Low |
| **LLM summary** | If output is too verbose, call a small/cheap model to summarize | Low (deferred) |

## Implementation Skeleton

```python
# filter/cleaner.py
from hooks import on

@on("after_execute")
def filter_worker_output(event):
    result = event.data["result"]
    findings = result.get("findings", [])

    # 1. Deduplicate by title
    seen = set()
    unique = []
    for f in findings:
        key = (f["type"], f["title"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    dropped = len(findings) - len(unique)

    # 2. Drop low confidence
    filtered = [f for f in unique if f.get("confidence", 1.0) >= 0.5]

    result["findings"] = filtered
    if dropped:
        result.setdefault("_filter_stats", {})["deduplicated"] = dropped
```

## Testing Filter Independently

Filter is a pure function of `event.data["result"]`. No blackboard, no LLM needed:

```python
from filter.cleaner import filter_worker_output
from hooks import HookEvent

ev = HookEvent("after_execute", {
    "task": {"id": "test"},
    "result": {
        "findings": [
            {"type": "asset", "title": "/admin", "confidence": 1.0},
            {"type": "asset", "title": "/admin", "confidence": 0.9},  # duplicate
            {"type": "vulnerability", "title": "XSS?", "confidence": 0.3},  # low conf
        ]
    }
})
filter_worker_output(ev)
assert len(ev.data["result"]["findings"]) == 1  # only the first /admin remains
```
