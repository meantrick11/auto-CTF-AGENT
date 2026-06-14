"""Layer 1 — Blackboard maintenance rules.

Triggers compaction when findings accumulate, cleans up stale data.
Pure rules, zero LLM cost (though compaction itself may call LLM).
"""

import re

# ── Compaction trigger ───────────────────────────────────────────

_FINDING_CHAR_THRESHOLD = 3000
_FINDING_COUNT_THRESHOLD = 25
_MAX_COMPACTIONS_PER_RUN = 5

_compaction_count = 0


def reset_compaction_counter():
    """Reset between runs."""
    global _compaction_count
    _compaction_count = 0


def should_compact(findings: list[dict]) -> bool:
    """Check if findings need compaction.

    Two triggers:
    1. Total data size exceeds character threshold
    2. Finding count exceeds count threshold
    """
    global _compaction_count
    if _compaction_count >= _MAX_COMPACTIONS_PER_RUN:
        return False

    total_chars = sum(
        len(str(f.get("data", {}))) + len(str(f.get("title", "")))
        for f in findings
    )

    if total_chars > _FINDING_CHAR_THRESHOLD:
        _compaction_count += 1
        return True
    if len(findings) > _FINDING_COUNT_THRESHOLD:
        _compaction_count += 1
        return True
    return False


# ── Observer notes for Commander ─────────────────────────────────

_observer_notes: list[dict] = []


def write_note(category: str, message: str, severity: str = "info"):
    """Write an observer note for Commander to see.

    Notes appear in Commander's compressed view (get_commander_view).
    """
    _observer_notes.append({
        "category": category,
        "message": message,
        "severity": severity,
    })


def get_observer_notes() -> list[dict]:
    """Get all observer notes for the current round."""
    return list(_observer_notes)


def reset_observer_notes():
    """Reset between runs."""
    global _observer_notes
    _observer_notes.clear()


# ── Summary generation for final report ──────────────────────────

def build_supervisor_summary(outcome: str, total_rounds: int,
                              findings: list[dict],
                              observer_notes: list[dict]) -> dict:
    """Generate a supervisor summary for the final mission report."""
    flag_findings = [f for f in findings if f.get("type") == "flag"]

    return {
        "outcome": outcome,
        "total_rounds": total_rounds,
        "total_findings": len(findings),
        "flag_captured": len(flag_findings) > 0,
        "warnings_issued": len([n for n in observer_notes if n["severity"] == "warn"]),
        "blocks_issued": len([n for n in observer_notes if n["severity"] == "block"]),
        "observer_notes": observer_notes[-10:],  # Last 10 only
    }
