"""Supervisor module — safety, drift, quality, and maintenance.

Three-Agent architecture:
  Commander  → tactical brain (decides what to do)
  Worker     → execution muscle (does it)
  Supervisor → immune system (watches both, intervenes when needed)

Supervisor monitors THROUGHOUT execution (via tool_trace in after_execute)
and can issue REDIRECTION orders that actively constrain Commander/Worker.

Architecture:
  Layer 1 (rules) — pure Python, zero LLM cost, runs on every hook
  Layer 2 (agent) — LLM semantic check, runs when Layer 1 flags "suspicious"
                    or when stuck/stagnation/dead-end is detected

Intervention escalation:
  write_note(warn) → Commander sees it, may or may not listen
  write_note(block) → before_task_create enforces it
  set_redirection() → before_task_create BLOCKS dead-end tasks,
                      before_plan warns Commander to pivot
"""

from hooks import on
from supervisor.safety import check_plan_safety, check_task_safety, check_code_safety
from supervisor.quality import dedup_within_task, normalize_finding, validate_finding
from supervisor.drift import (
    check_stagnation, check_repetition,
    check_consecutive_failures, check_commander_loop,
    record_task_result, reset_tracker,
)
from supervisor.maintenance import (
    should_compact, write_note, get_observer_notes,
    reset_observer_notes, reset_compaction_counter,
)


# ── Redirection: stronger than observer_notes ────────────────────
# When Supervisor detects a dead-end, it issues a redirection that
# actively blocks certain task types and suggests alternatives.

_redirection: dict = {
    "active": False,
    "blocked_types": [],       # Task types to block completely
    "blocked_targets": [],     # Specific URLs/params to avoid
    "suggested": "",           # What Commander should try instead
    "reason": "",
}


def set_redirection(blocked_types: list[str], suggested: str, reason: str):
    """Issue a redirection order. before_task_create will enforce it."""
    _redirection["active"] = True
    _redirection["blocked_types"] = blocked_types
    _redirection["suggested"] = suggested
    _redirection["reason"] = reason


def clear_redirection():
    """Clear redirection when situation improves."""
    _redirection["active"] = False
    _redirection["blocked_types"] = []
    _redirection["blocked_targets"] = []
    _redirection["suggested"] = ""
    _redirection["reason"] = ""


def _is_blocked_by_redirection(task_def: dict) -> tuple[bool, str]:
    """Check if a task should be blocked by active redirection."""
    if not _redirection["active"]:
        return False, ""

    task_type = task_def.get("type", "")
    instruction = task_def.get("instruction", "")

    if task_type in _redirection["blocked_types"]:
        return True, (
            f"REDIRECTION: [{task_type}] is blocked. {_redirection['suggested']}"
        )

    # Also check if instruction targets a blocked target
    for target in _redirection.get("blocked_targets", []):
        if target.lower() in instruction.lower():
            return True, (
                f"REDIRECTION: target '{target}' is a known dead end. "
                f"{_redirection['suggested']}"
            )

    return False, ""


# ── Agent (lazy init — created once on first use) ────────────────
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from supervisor.agent import SupervisorAgent
        _agent = SupervisorAgent()
    return _agent


def _escalate_to_agent(event_type: str, snapshot: dict,
                        flagged_data: dict) -> dict:
    """Call Layer 2 Agent for semantic judgment."""
    agent = _get_agent()
    result = agent.review(event_type, snapshot, flagged_data)
    action = result.get("supervisor_action", "warn")

    for note in result.get("observer_notes", []):
        write_note(
            category=note.get("category", "drift"),
            message=note.get("message", ""),
            severity=note.get("severity", "info"),
        )

    # If Agent says block, issue redirection
    if action == "block" and flagged_data.get("stuck_detected"):
        redirect = result.get("redirect_to", "")
        reason = result.get("reasoning", "")
        task_type = flagged_data.get("task_type", "")
        set_redirection(
            blocked_types=[task_type] if task_type else [],
            suggested=redirect or "Pivot to a different attack surface",
            reason=reason,
        )

    return {"action": action, "reasoning": result.get("reasoning", "")}


# ── Hook: before_plan ────────────────────────────────────────────

@on("before_plan")
def _on_before_plan(event):
    """Check blackboard state sanity before Commander plans."""
    snapshot = event.data.get("snapshot", {})

    goal = snapshot.get("goal", {})
    if not goal or not goal.get("description"):
        event.block("No goal on blackboard")
        write_note("safety", "before_plan blocked: no goal defined", "block")
        return

    # If redirection is active, inject it into the snapshot for Commander
    if _redirection["active"]:
        snapshot["_redirection"] = dict(_redirection)

    # Check stagnation
    findings = snapshot.get("findings", [])
    is_stagnant, note = check_stagnation(len(findings))
    if is_stagnant:
        write_note("drift", note, "warn")


# ── Hook: after_plan ─────────────────────────────────────────────

@on("after_plan")
def _on_after_plan(event):
    """Validate Commander decisions."""
    decision = event.data.get("decision")
    snapshot = event.data.get("snapshot", {})
    if not decision:
        return

    # Layer 1: rule-based checks
    is_safe, issues = check_plan_safety(decision)

    if not is_safe:
        flagged = {
            "issues": issues,
            "new_tasks": [
                {"type": t.get("type"), "instruction": t.get("instruction", "")[:200]}
                for t in decision.new_tasks
            ],
        }
        result = _escalate_to_agent("after_plan", snapshot, flagged)
        if result["action"] == "block":
            write_note("safety",
                f"after_plan blocked: {issues[0].get('reason', 'unknown')}", "block")

    # Check for Commander loop
    is_looping, loop_note = check_commander_loop(decision)
    if is_looping:
        write_note("drift", loop_note, "warn")
        flagged = {"loop_detection": loop_note}
        _escalate_to_agent("after_plan", snapshot, flagged)

    # Check if Commander is ignoring redirection
    if _redirection["active"] and decision.new_tasks:
        all_blocked = all(
            t.get("type") in _redirection["blocked_types"]
            for t in decision.new_tasks
        )
        if all_blocked:
            write_note("drift",
                f"Commander ignoring REDIRECTION: all new tasks are blocked types. "
                f"Redirection says: {_redirection['suggested']}",
                "block")


# ── Hook: before_task_create ─────────────────────────────────────

@on("before_task_create")
def _on_before_task_create(event):
    """Safety check + repetition detection + redirection enforcement."""
    task_def = event.data.get("task_def", {})

    # Layer 1: safety
    is_safe, reason = check_task_safety(task_def)
    if not is_safe:
        event.block(reason)
        write_note("safety", f"before_task_create blocked: {reason}", "block")
        return

    # ── REDIRECTION enforcement (strongest check) ──
    is_blocked, block_reason = _is_blocked_by_redirection(task_def)
    if is_blocked:
        event.block(block_reason)
        write_note("drift", f"before_task_create blocked by redirection: {block_reason}", "block")
        return

    # Layer 1: repetition
    is_repeat, note = check_repetition(task_def)
    if is_repeat:
        snapshot = event.data.get("snapshot", {})
        flagged = {"repetition_detected": note, "task_def": task_def}
        result = _escalate_to_agent("before_task_create", snapshot, flagged)
        if result["action"] == "block":
            event.block(note)
            write_note("drift", f"before_task_create blocked (repetition): {note}", "block")
        else:
            write_note("drift", note, "warn")


# ── Hook: before_execute ─────────────────────────────────────────

@on("before_execute")
def _on_before_execute(event):
    """Last safety gate before Worker execution."""
    task = event.data.get("task", {})
    instruction = task.get("instruction", "")

    is_safe, reason = check_task_safety(task)
    if not is_safe:
        event.block(reason)
        write_note("safety", f"before_execute blocked: {reason}", "block")


# ── Hook: after_execute ──────────────────────────────────────────

@on("after_execute")
def _on_after_execute(event):
    """Filter findings, detect worker problems via tool_trace, track results.

    This is the Supervisor's main monitoring point — it reads the Worker's
    tool_trace and decides whether to issue a redirection.
    """
    result = event.data.get("result")
    task = event.data.get("task", {})

    # ── Quality: dedup + normalize findings ──
    if result:
        findings = result.findings if hasattr(result, 'findings') else result.get("findings", [])
        if findings and isinstance(findings, list):
            dict_findings = []
            for f in findings:
                if isinstance(f, dict):
                    dict_findings.append(f)
                elif hasattr(f, 'type'):
                    dict_findings.append({
                        "type": f.type,
                        "title": f.title,
                        "data": f.data if hasattr(f, 'data') else {},
                        "confidence": f.confidence if hasattr(f, 'confidence') else 0.7,
                    })
                else:
                    dict_findings.append(f)

            cleaned = dedup_within_task(dict_findings)
            for f in cleaned:
                f = normalize_finding(f)
                validate_finding(f)

            if hasattr(result, 'findings'):
                result.findings = cleaned
            else:
                result["findings"] = cleaned

        # ── Track for drift detection ──
        status = result.status if hasattr(result, 'status') else result.get("status", "completed")
        record_task_result(task, status)

        # ── Tool trace analysis → may trigger redirection ──
        _analyze_and_intervene(result, task, event.data.get("snapshot", {}))

    # ── Consecutive failure check ──
    task_type = task.get("type", "")
    should_abandon, note = check_consecutive_failures(task_type)
    if should_abandon:
        write_note("drift", note, "warn")
        snapshot = event.data.get("snapshot", {})
        _escalate_to_agent("after_execute", snapshot, {
            "consecutive_failures": note,
            "task_type": task_type,
        })
        # Issue redirection for this dead-end task type
        set_redirection(
            blocked_types=[task_type],
            suggested="This attack surface is not viable. Explore other endpoints or attack vectors.",
            reason=note,
        )

    # ── If task succeeded with new findings, clear redirection ──
    if result:
        status = result.status if hasattr(result, 'status') else result.get("status", "")
        findings = result.findings if hasattr(result, 'findings') else result.get("findings", [])
        if status == "completed" and len(findings) > 0:
            has_substantial = any(
                (f.get("type") if isinstance(f, dict) else getattr(f, 'type', ''))
                in ("flag", "credential", "vulnerability")
                for f in findings
            )
            if has_substantial:
                clear_redirection()


def _analyze_and_intervene(result, task: dict, snapshot: dict):
    """Read Worker's tool_trace and intervene if stuck.

    Escalation path:
      1. Detect stuck from tool_trace (Layer 1 rule)
      2. Escalate to Supervisor Agent for semantic analysis
      3. Agent returns redirection → enforced by before_task_create
    """
    error_detail = result.error_detail if hasattr(result, 'error_detail') else result.get("error_detail", {})
    if not error_detail:
        return
    tool_trace = error_detail.get("tool_trace", [])
    if not tool_trace:
        return

    task_type = task.get("type", "")
    task_id = task.get("id", "")[:8]

    # Count consecutive same-tool errors
    last_tool = None
    error_streak = 0
    for entry in tool_trace:
        tool = entry.get("tool", "")
        has_error = entry.get("has_error", False)
        if tool == last_tool and has_error:
            error_streak += 1
        else:
            error_streak = 1 if has_error else 0
            last_tool = tool

    # Count overall error rate
    all_errors = [e for e in tool_trace if e.get("has_error")]
    error_rate = len(all_errors) / len(tool_trace) if tool_trace else 0

    needs_intervention = False
    reason = ""

    if error_streak >= 5:
        needs_intervention = True
        reason = f"tool '{last_tool}' failed {error_streak}x consecutively"
    elif error_rate >= 0.7 and len(tool_trace) >= 4:
        needs_intervention = True
        reason = f"{len(all_errors)}/{len(tool_trace)} tool calls errored"

    if needs_intervention:
        # Escalate to Agent for full analysis
        result = _escalate_to_agent("after_execute", snapshot, {
            "stuck_detected": True,
            "task_type": task_type,
            "task_id": task_id,
            "reason": reason,
            "tool_trace": tool_trace,
            "findings_so_far": snapshot.get("findings", [])[-5:],
        })

        if result["action"] == "block":
            write_note("drift",
                f"Task {task_id} ({task_type}): INTERVENTION — {reason}. "
                f"Redirection active. Commander must pivot.",
                "block")


# ── Hook: on_finding ─────────────────────────────────────────────

@on("on_finding")
def _on_on_finding(event):
    """Validate individual findings before they enter blackboard."""
    finding = event.data.get("finding", {})
    if isinstance(finding, dict):
        is_valid, reason = validate_finding(finding)
        if not is_valid:
            write_note("quality", f"Finding rejected: {reason}", "warn")


# ── Hook: on_complete ────────────────────────────────────────────

@on("on_complete")
def _on_on_complete(event):
    """Clean up and write final notes."""
    reset_tracker()
    reset_observer_notes()
    reset_compaction_counter()
    clear_redirection()


# ── Public API ───────────────────────────────────────────────────

def init_supervisor():
    """Called by engine at mission start to reset state."""
    reset_tracker()
    reset_observer_notes()
    reset_compaction_counter()
    clear_redirection()


__all__ = [
    "init_supervisor",
    "should_compact",
    "get_observer_notes",
    "write_note",
]
