"""Shared utilities."""

import json
import re


def extract_json(text: str) -> dict | None:
    """Robustly extract a JSON object from text that may contain surrounding prose.

    Uses bracket counting to find the outermost {...} block, then tries to parse it.
    Fallback: regex extraction from markdown code blocks.
    """
    if not text:
        return None

    # 1. Direct parse (pure JSON)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Find outermost {...} via bracket counting
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\" and in_string:
            escape = True
            continue

        if ch == '"' and not escape:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Try next { block
                    start = text.find("{", start + 1)
                    if start == -1:
                        return None
                    depth = 0
                    continue

    # 3. Markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    return None
