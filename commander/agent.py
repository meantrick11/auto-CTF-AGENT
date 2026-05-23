"""Commander agent — tactical planner, no tool execution."""

import json
import os

from config import DEEPSEEK_MODEL, create_client
from utils import extract_json


class Commander:
    """Reads the blackboard, reasons about the situation, and generates subtasks.

    The Commander does NOT execute any security tools.
    It only reads state and writes task definitions.
    """

    def __init__(self, model: str | None = None):
        self.model = model or DEEPSEEK_MODEL
        self._client = create_client(model)
        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "system_prompt.txt"
        )
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_prompt = f.read()

    def plan(self, snapshot: dict) -> dict:
        """Analyze blackboard state and decide next actions.

        Returns:
            {
                "decision": "continue" | "completed" | "failed",
                "reasoning": "...",
                "new_tasks": [{type, instruction, input_data}, ...],
                "final_summary": "..."
            }
        """
        user_message = self._build_snapshot_message(snapshot)

        try:
            return self._call_llm(user_message)
        except Exception as exc:
            return {
                "decision": "failed",
                "reasoning": f"Commander error: {exc}",
                "new_tasks": [],
                "final_summary": "",
            }

    def _build_snapshot_message(self, snapshot: dict) -> str:
        goal = snapshot.get("goal", {})
        tasks = snapshot.get("tasks", [])
        findings = snapshot.get("findings", [])
        events = snapshot.get("recent_events", [])

        parts = [
            "## Current Goal",
            f"Description: {goal.get('description', 'N/A')}",
            f"Status: {goal.get('status', 'N/A')}",
            "",
            "## Task Status",
        ]

        if tasks:
            for t in tasks:
                parts.append(
                    f"- [{t.get('status')}] {t.get('type')}: "
                    f"{t.get('instruction', '')[:100]}"
                )
                if t.get("output_data"):
                    parts.append(
                        f"  Output: {json.dumps(t['output_data'], ensure_ascii=False)[:200]}"
                    )
        else:
            parts.append("(no tasks yet)")

        parts.append("")
        parts.append("## Findings")
        if findings:
            for f in findings:
                parts.append(
                    f"- [{f.get('type')}] {f.get('title')} "
                    f"(confidence: {f.get('confidence', 1.0)})"
                )
                if f.get("data"):
                    parts.append(
                        f"  Data: {json.dumps(f['data'], ensure_ascii=False)[:150]}"
                    )
        else:
            parts.append("(no findings yet)")

        parts.append("")
        parts.append("## Recent Events")
        if events:
            for e in events[-10:]:
                parts.append(
                    f"[{e.get('timestamp', '')}] {e.get('agent_name')}: "
                    f"{e.get('action')} — {e.get('detail', '')[:80]}"
                )
        else:
            parts.append("(no events yet)")

        parts.append("")
        parts.append("Based on the above state, decide the next tactical step. ")
        parts.append(
            "Output ONLY a valid JSON object with decision, reasoning, "
            "new_tasks, and final_summary."
        )

        return "\n".join(parts)

    def _call_llm(self, user_message: str) -> dict:
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        text = response.choices[0].message.content or ""
        return self._parse_output(text)

    def _parse_output(self, text: str) -> dict:
        result = extract_json(text)
        if result:
            return result
        return {
            "decision": "failed",
            "reasoning": f"Could not parse Commander output: {text[:300]}",
            "new_tasks": [],
            "final_summary": "",
        }
