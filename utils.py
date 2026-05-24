"""Shared utilities."""

import json
import re
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)


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


def retry_llm_call(fn, max_retries=3, base_delay=1.0):
    """Call fn with exponential backoff on transient API errors.

    Retries on: rate limits (429), server errors (5xx),
    connection errors, and timeouts.
    Does NOT retry on: auth errors (401), bad requests (400).
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except (APIConnectionError, APITimeoutError,
                InternalServerError, RateLimitError) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"[Retry] {type(exc).__name__}, "
                      f"retrying in {delay:.1f}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
        except APIStatusError as exc:
            if exc.status_code >= 500:
                last_exc = exc
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    print(f"[Retry] HTTP {exc.status_code}, "
                          f"retrying in {delay:.1f}s "
                          f"(attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore
