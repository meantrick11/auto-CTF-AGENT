"""Filter — rule-based data washer. Hooks into after_execute.

Safe operations only (never drops data):
  1. Dedup findings by (type, title) — merge, take higher confidence
  2. Normalize — ensure all required fields present
  3. Truncate display — mark large data but keep original intact
"""

from hooks import on


MAX_DATA_DISPLAY = 500


@on("after_execute")
def filter_worker_output(event):
    """Clean worker output before it hits the blackboard.

    Modifies event.data["result"] in place.
    """
    result = event.data.get("result")
    if result is None:
        return

    # Normalize to TaskResult
    from workers.base_worker import TaskResult
    if isinstance(result, TaskResult):
        task_result = result
    elif isinstance(result, dict):
        task_result = TaskResult.from_dict(result)
    else:
        return

    findings = task_result.findings
    if not findings:
        return

    # ── 1. Dedup by (type, title) — merge, take higher confidence ──
    seen = {}
    for f in findings:
        key = (f.type, f.title)
        if key in seen:
            existing = seen[key]
            existing.confidence = max(existing.confidence, f.confidence)
            # Merge data dicts (existing takes priority, new fills gaps)
            for k, v in f.data.items():
                if k not in existing.data:
                    existing.data[k] = v
        else:
            seen[key] = f

    unique = list(seen.values())
    dropped = len(findings) - len(unique)

    # ── 2. Normalize — ensure required fields ──
    for f in unique:
        if not f.type:
            f.type = "info"
        if not f.title:
            f.title = "untitled"

    # ── 3. Truncate display — mark large data, keep original ──
    for f in unique:
        data_str = str(f.data)
        if len(data_str) > MAX_DATA_DISPLAY:
            f.data["_truncated"] = True
            f.data["_original_size"] = len(data_str)

    task_result.findings = unique
    if dropped:
        task_result.output_data.setdefault("_filter_stats", {})
        task_result.output_data["_filter_stats"]["deduplicated"] = dropped

    event.data["result"] = task_result
