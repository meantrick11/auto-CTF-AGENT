"""Layer 1 — Drift detection & repetition monitoring (formerly evaluator/).

Detects when Commander is repeating itself, Worker is stuck,
or the mission is going nowhere. Pure rules, zero LLM cost.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher


# ── In-memory tracking (per-run, not persisted) ──────────────────

@dataclass
class _RunTracker:
    """Tracks task execution patterns across rounds for drift detection."""
    task_history: list[dict] = field(default_factory=list)
    finding_counts_per_round: list[int] = field(default_factory=list)
    failed_task_types: dict[str, int] = field(default_factory=dict)
    tool_call_counts: dict[str, int] = field(default_factory=dict)  # (task_id, tool_name) → count

    def reset(self):
        self.task_history.clear()
        self.finding_counts_per_round.clear()
        self.failed_task_types.clear()
        self.tool_call_counts.clear()


_tracker = _RunTracker()


def reset_tracker():
    """Reset tracker between runs. Called by engine on mission start."""
    _tracker.reset()


# ── Stagnation detection ─────────────────────────────────────────

def check_stagnation(current_finding_count: int) -> tuple[bool, str]:
    """Check if no new findings in recent rounds.

    Returns (is_stagnant, note).
    """
    _tracker.finding_counts_per_round.append(current_finding_count)

    if len(_tracker.finding_counts_per_round) >= 3:
        last_3 = _tracker.finding_counts_per_round[-3:]
        if last_3[-1] == last_3[-2] == last_3[0]:
            return True, "Stagnation: no new findings in last 3 rounds"
    return False, ""


# ── Repetition detection ─────────────────────────────────────────

def _instruction_similarity(a: str, b: str) -> float:
    """Rough similarity between two instructions."""
    return SequenceMatcher(None, a[:200], b[:200]).ratio()


def check_repetition(task_def: dict) -> tuple[bool, str]:
    """Check if this task is too similar to a previously failed one.

    Returns (is_repeat, note).
    """
    instruction = task_def.get("instruction", "")
    task_type = task_def.get("type", "")

    for hist in _tracker.task_history:
        if hist.get("status") != "failed":
            continue
        if hist.get("type") != task_type:
            continue
        hist_instruction = hist.get("instruction", "")
        sim = _instruction_similarity(instruction, hist_instruction)
        if sim > 0.7:
            return True, (
                f"Repetition: task type '{task_type}' with similar instruction "
                f"(similarity={sim:.0%}) already failed. Suggest pivoting."
            )

    return False, ""


def record_task_result(task_def: dict, status: str):
    """Record a task result for future repetition detection."""
    _tracker.task_history.append({
        "type": task_def.get("type", ""),
        "instruction": task_def.get("instruction", ""),
        "status": status,
    })

    if status == "failed":
        ttype = task_def.get("type", "")
        _tracker.failed_task_types[ttype] = _tracker.failed_task_types.get(ttype, 0) + 1


# ── Worker stuck detection ───────────────────────────────────────

def check_worker_stuck(task_id: str, tool_name: str, tool_result: dict) -> tuple[bool, str]:
    """Track consecutive same-tool calls. Flag if a tool is called
    too many times with errors in the same task.

    Only counts TOOL-LEVEL errors (connection_error, timeout, unknown),
    NOT application-level error responses (HTTP 401, 500, etc.).

    Returns (is_stuck, note).
    """
    key = f"{task_id}:{tool_name}"

    # Only count tool-level errors: explicit error key with error_type
    # or status_code=0 (connection failure). NOT HTTP responses with "error" in body.
    is_tool_error = False
    if isinstance(tool_result, dict):
        err = tool_result.get("error")
        err_type = tool_result.get("error_type")
        status_code = tool_result.get("status_code")
        # Tool error: has error key with an error_type, or status_code=0 (connection failure)
        if err and err_type:
            is_tool_error = True
        elif status_code == 0 and err:
            is_tool_error = True

    if is_tool_error:
        _tracker.tool_call_counts[key] = _tracker.tool_call_counts.get(key, 0) + 1
    else:
        _tracker.tool_call_counts[key] = 0

    if _tracker.tool_call_counts.get(key, 0) >= 5:
        return True, (
            f"Worker stuck: tool '{tool_name}' called {_tracker.tool_call_counts[key]}x "
            f"consecutively with errors in task {task_id[:8]}"
        )

    return False, ""


def check_consecutive_failures(task_type: str) -> tuple[bool, str]:
    """Check if the same task type has failed twice in a row.

    Returns (should_abandon, note).
    """
    count = _tracker.failed_task_types.get(task_type, 0)
    if count >= 2:
        return True, (
            f"Dead end: task type '{task_type}' failed {count}x consecutively. "
            "Suggest Commander abandon this attack surface."
        )
    return False, ""


# ── Commander loop detection ─────────────────────────────────────

def check_commander_loop(decision) -> tuple[bool, str]:
    """Detect if Commander is issuing the same directions as last round.

    Returns (is_looping, note).
    """
    current_instructions = [
        t.get("instruction", "") for t in decision.new_tasks
    ]

    # Compare with last round's completed/failed tasks
    recent = _tracker.task_history[-5:] if _tracker.task_history else []
    recent_instructions = [t.get("instruction", "") for t in recent]

    if not recent_instructions or not current_instructions:
        return False, ""

    # Check if any current instruction is near-identical to a recent one
    for cur in current_instructions:
        for hist in recent_instructions:
            if _instruction_similarity(cur, hist) > 0.85:
                return True, (
                    f"Commander loop: instruction '{cur[:80]}...' "
                    f"is near-identical to a recent task."
                )

    return False, ""
