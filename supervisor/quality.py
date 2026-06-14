"""Layer 1 — Finding quality control (formerly filter/).

Dedup, normalize, truncate. Pure rules, zero LLM cost.
"""

from typing import Any


def normalize_finding(finding: dict) -> dict:
    """Fill missing fields with safe defaults. Never drops data."""
    if "type" not in finding or not finding["type"]:
        finding["type"] = "info"
    if "title" not in finding or not finding["title"]:
        finding["title"] = "untitled"
    if "confidence" not in finding or finding["confidence"] is None:
        finding["confidence"] = 0.4
    if "data" not in finding:
        finding["data"] = {}
    return finding


def _data_size(data: Any) -> int:
    """Rough character count for a finding's data field."""
    if isinstance(data, dict):
        return sum(len(str(v)) for v in data.values())
    return len(str(data))


def truncate_if_large(finding: dict, max_chars: int = 500) -> dict:
    """Mark large data as truncated. Never drops data, only flags it."""
    if _data_size(finding.get("data", {})) > max_chars:
        finding["_truncated"] = True
        finding["_original_size"] = _data_size(finding["data"])
    return finding


def dedup_within_task(findings: list[dict]) -> list[dict]:
    """Merge findings within a single task by (type, title).

    Keeps the one with higher confidence, merges data dicts.
    Never drops findings — always returns the merged set.
    """
    seen: dict[tuple, dict] = {}
    for f in findings:
        f = normalize_finding(f)
        key = (f["type"], f["title"])
        if key in seen:
            existing = seen[key]
            if f.get("confidence", 0) > existing.get("confidence", 0):
                # Keep higher-confidence version, merge data
                merged_data = {**existing.get("data", {}), **f.get("data", {})}
                f["data"] = merged_data
                seen[key] = f
            else:
                existing["data"] = {**existing.get("data", {}), **f.get("data", {})}
        else:
            seen[key] = f

    return list(seen.values())


def validate_finding(finding: dict) -> tuple[bool, str]:
    """Check if a finding is well-formed.

    Returns (is_valid, reason_if_not).
    """
    VALID_TYPES = {"vulnerability", "credential", "flag", "asset", "info"}

    ftype = finding.get("type", "")
    if ftype not in VALID_TYPES:
        return False, f"Invalid finding type: '{ftype}'"

    title = finding.get("title", "")
    if not title or len(title) < 2:
        return False, "Title too short or missing"

    confidence = finding.get("confidence", 1.0)
    if not (0.0 <= confidence <= 1.0):
        return False, f"Confidence out of range: {confidence}"

    return True, ""
