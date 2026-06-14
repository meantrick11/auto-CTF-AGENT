"""Layer 1 — Safety rules (formerly guardrail/).

All checks are pure rules: regex + string matching. Zero LLM cost.
"""

import re
from typing import Optional

# ── Dangerous patterns ──────────────────────────────────────────

_DANGER_PATTERNS = [
    # Shell command execution
    (r"\bos\.system\b", "block", "os.system() — forbidden shell command execution"),
    (r"\bsubprocess\b", "block", "subprocess — forbidden shell command execution"),
    (r"\bexec\s*\(", "block", "exec() — nested code execution disallowed"),
    (r"\beval\s*\(", "block", "eval() — nested code execution disallowed"),
    (r"\bcompile\s*\(", "block", "compile() — code compilation disallowed"),
    (r"\b__import__\b", "block", "__import__ — sandbox escape attempt"),

    # File system destruction
    (r"\bshutil\.rmtree\b", "block", "shutil.rmtree() — forbidden destructive operation"),
    (r"\bos\.remove\b", "block", "os.remove() — file deletion disallowed"),
    (r"\bos\.unlink\b", "block", "os.unlink() — file deletion disallowed"),

    # Suspicious imports
    (r"\bimport\s+os\b", "block", "import os — system module disallowed"),
    (r"\bimport\s+sys\b", "block", "import sys — system module disallowed"),
    (r"\bimport\s+shutil\b", "block", "import shutil — file tools disallowed"),
    (r"\bimport\s+ctypes\b", "block", "import ctypes — native code disallowed"),

    # File I/O (warn, not block — may be needed for legit encoding tasks)
    (r"\bopen\s*\(.+[\"']w[\"']", "warn", "open() with write mode — file modification"),
    (r"\bopen\s*\(.+[\"']a[\"']", "warn", "open() with append mode — file modification"),
]


def check_code_safety(code: str) -> tuple[bool, list[dict]]:
    """Scan code for dangerous patterns.

    Returns (is_safe, [matches]).
    """
    matches = []
    for pattern, severity, message in _DANGER_PATTERNS:
        if re.search(pattern, code):
            matches.append({
                "pattern": pattern,
                "severity": severity,
                "message": message,
            })

    is_safe = not any(m["severity"] == "block" for m in matches)
    return is_safe, matches


# ── Task safety check ────────────────────────────────────────────

# Known tools the Worker actually has (synced with ToolRegistry)
_KNOWN_TOOLS = {
    "http_get", "http_post",
    "web_directory_scan", "web_extract_forms", "web_analyze_headers",
    "web_sqli_test", "web_xss_test", "web_command_injection_test",
    "base64_encode", "base64_decode",
    "hex_encode", "hex_decode",
    "url_encode", "url_decode",
    "rot13",
}

# Tools that Commander might hallucinate — we've seen these in logs
_HALLUCINATION_KEYWORDS = [
    r"\bBurp\s*Suite\b", r"\bBurp\b",
    r"\bWireshark\b", r"\btcpdump\b",
    r"\bproxy\b", r"\bintercept\b",
    r"\bsave\s+to\s+file\b", r"\bwrite\s+to\s+disk\b",
    r"\bscreenshot\b", r"\bbrowser\b",
    r"\bheadless\s*chrome\b", r"\bpuppeteer\b",
    r"\bselenium\b",
    r"\bssh\b", r"\bnc\s+", r"\bnetcat\b",
    r"\bnmap\b", r"\bsqlmap\b", r"\bhydra\b",
]


def check_task_safety(task_def: dict) -> tuple[bool, Optional[str]]:
    """Check if a task definition is achievable with existing tools.

    Returns (is_safe, reason_if_unsafe).
    """
    task_type = task_def.get("type", "")
    instruction = task_def.get("instruction", "")

    # Valid task types
    if task_type not in ("web_recon", "web_exploit"):
        return False, f"Unknown task type: '{task_type}' (only web_recon/web_exploit exist)"

    # Check for hallucinated tools in instruction
    for pattern in _HALLUCINATION_KEYWORDS:
        if re.search(pattern, instruction, re.IGNORECASE):
            return False, f"Instruction references unavailable capability: {pattern}"

    return True, None


def check_plan_safety(decision) -> tuple[bool, list[dict]]:
    """Check all tasks in a Commander decision for safety issues.

    Returns (all_safe, [issues]).
    """
    issues = []
    for task_def in decision.new_tasks:
        is_safe, reason = check_task_safety(task_def)
        if not is_safe:
            issues.append({
                "task_type": task_def.get("type"),
                "instruction": task_def.get("instruction", "")[:100],
                "reason": reason,
            })
    return len(issues) == 0, issues
