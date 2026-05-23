"""Web security specialist worker."""

import json
import os

from config import DEEPSEEK_MODEL, create_client
from utils import extract_json

from workers.base_worker import BaseWorker, TaskResult
from tools.registry import get_registry


class WebWorker(BaseWorker):
    """Executes web reconnaissance and exploitation tasks.

    Uses LLM function calling (DeepSeek / OpenAI-compatible) to decide
    which tools to invoke, then extracts structured findings.
    """

    name = "web_worker"
    domain = "web"

    def __init__(self, model: str | None = None):
        self.model = model or DEEPSEEK_MODEL
        self._client = create_client(model)
        registry = get_registry()
        self.tools = registry.get_multi(["shared", "web"])

        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "system_prompt.txt"
        )
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_prompt = f.read()

    def execute(self, task: dict, blackboard_snapshot: dict) -> TaskResult:
        task_id = task.get("id", "")
        instruction = task.get("instruction", "")
        input_data = task.get("input_data", {})

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._build_user_message(
                instruction, input_data, blackboard_snapshot
            )},
        ]

        try:
            result = self._agent_loop(messages)
            for f in result.findings:
                f.source_task_id = task_id
            return result
        except Exception as exc:
            return TaskResult(
                status="failed",
                summary=f"Worker error: {exc}",
                output_data={"error": str(exc)},
            )

    def _build_user_message(self, instruction: str, input_data: dict,
                            snapshot: dict) -> str:
        parts = [
            "## Task Instruction",
            instruction,
            "",
            "## Input Data",
            json.dumps(input_data, ensure_ascii=False, indent=2),
        ]

        findings = snapshot.get("findings", [])
        if findings:
            parts.append("")
            parts.append("## Known Findings (from previous tasks)")
            parts.append(
                json.dumps(findings, ensure_ascii=False, indent=2)
            )

        parts.append("")
        parts.append(
            "Execute the task above using your available tools. "
            "After all tool calls, output your final result as a JSON object "
            "with 'status', 'summary', and 'findings'."
        )
        return "\n".join(parts)

    def _agent_loop(self, messages: list[dict]) -> TaskResult:
        """Run LLM + tool-calling loop. Max 8 iterations."""
        tool_schemas = [t.to_openai_tool() for t in self.tools]

        for _ in range(8):
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=messages,
                tools=tool_schemas,
            )

            choice = response.choices[0]
            msg = choice.message

            # If no tool calls, parse final output
            if not msg.tool_calls:
                text = msg.content or ""
                return self._parse_final_output(text)

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each tool and append results
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = self._call_tool(tool_name, args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        return TaskResult(
            status="failed",
            summary="Max tool-calling iterations reached without final output",
        )

    def _call_tool(self, name: str, inputs: dict) -> dict:
        registry = get_registry()
        try:
            result = registry.call(name, **inputs)
            return result if isinstance(result, dict) else {"result": str(result)}
        except Exception as exc:
            return {"error": str(exc)}

    def _parse_final_output(self, text: str) -> TaskResult:
        parsed = extract_json(text)
        if parsed:
            return TaskResult.from_dict(parsed)
        return TaskResult(
            status="completed",
            summary=text[:500],
            output_data={"raw_response": text},
        )
