"""Layer 2 — Supervisor Agent (LLM-based semantic checks).

Called ONLY when Layer 1 rules flag something as "suspicious".
Lightweight compared to Commander/Worker — runs at most 1-2 times per round.
"""

import json
import os

from config import DEEPSEEK_MODEL, create_client
from utils import extract_json, retry_llm_call


class SupervisorAgent:
    """Semantic safety & drift assessment using LLM.

    Does NOT run on every hook — only when Layer 1 rules escalate.
    """

    def __init__(self, model: str | None = None):
        self.model = model or DEEPSEEK_MODEL
        self._client = create_client(model)

        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "system_prompt.txt"
        )
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_prompt = f.read()

    def review(self, event_type: str, snapshot: dict,
               flagged_data: dict) -> dict:
        """Review a flagged event and decide: allow, warn, or block.

        Args:
            event_type: Which hook triggered this (after_plan, before_execute, etc.)
            snapshot: Blackboard commander_view
            flagged_data: The specific data that Layer 1 rules flagged

        Returns:
            {"supervisor_action": "allow|warn|block",
             "observer_notes": [...],
             "reasoning": "..."}
        """
        user_message = self._build_message(event_type, snapshot, flagged_data)

        try:
            return self._call_llm(user_message)
        except Exception:
            # Agent failure → default to "warn" (safe fallback, never block on error)
            return {
                "supervisor_action": "warn",
                "observer_notes": [
                    {"category": "system",
                     "message": "Supervisor Agent unavailable — flagged by rules, defaulting to warn",
                     "severity": "warn"}
                ],
                "reasoning": "Supervisor Agent call failed, falling back to warn",
            }

    def _build_message(self, event_type: str, snapshot: dict,
                       flagged_data: dict) -> str:
        parts = [
            f"## Trigger Event: {event_type}",
            "Layer 1 rules flagged this event as suspicious. Review it.",
            "",
            "## Blackboard State (Commander View)",
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            "",
            "## Flagged Data",
            json.dumps(flagged_data, ensure_ascii=False, indent=2),
            "",
            "Decide: allow, warn, or block? Output ONLY valid JSON.",
        ]
        return "\n".join(parts)

    def _call_llm(self, user_message: str) -> dict:
        response = retry_llm_call(
            lambda: self._client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        )

        text = response.choices[0].message.content or ""
        parsed = extract_json(text)
        if parsed:
            return {
                "supervisor_action": parsed.get("supervisor_action", "warn"),
                "observer_notes": parsed.get("observer_notes", []),
                "reasoning": parsed.get("reasoning", ""),
            }

        return {
            "supervisor_action": "warn",
            "observer_notes": [],
            "reasoning": "Failed to parse Supervisor Agent output",
        }
