"""Central tool registry — decorator-based registration + JSON Schema generation."""

from dataclasses import dataclass, field
from typing import Callable, Any
import inspect
import re


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict          # JSON Schema for function calling
    category: str             # "shared" | "web" | "crypto" | ...
    func: Callable = field(repr=False)

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class ToolRegistry:
    """Global registry for all tools."""

    _instance: "ToolRegistry | None" = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: dict[str, ToolDef] = {}
        return cls._instance

    def register(self, func: Callable, category: str,
                 description: str) -> ToolDef:
        params_schema = _build_json_schema(func)
        tool = ToolDef(
            name=func.__name__,
            description=description,
            parameters=params_schema,
            category=category,
            func=func,
        )
        self._tools[func.__name__] = tool
        return tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def get_by_category(self, category: str) -> list[ToolDef]:
        return [t for t in self._tools.values() if t.category == category]

    def get_multi(self, categories: list[str]) -> list[ToolDef]:
        return [t for t in self._tools.values() if t.category in categories]

    def list_all(self) -> list[ToolDef]:
        return list(self._tools.values())

    def call(self, name: str, **kwargs) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Tool not found: {name}")
        return tool.func(**kwargs)

    def to_openai_tools(self, categories: list[str] | None = None) -> list[dict]:
        tools = self.get_multi(categories) if categories else self.list_all()
        return [t.to_openai_tool() for t in tools]


# Singleton access
def get_registry() -> ToolRegistry:
    return ToolRegistry()


def register_tool(category: str, description: str):
    """Decorator to register a function as a tool."""
    def decorator(func: Callable):
        get_registry().register(func, category, description)
        return func
    return decorator


# ── JSON Schema generation from type hints ────────────────────────

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


def _parse_param_descriptions(func: Callable) -> dict[str, str]:
    """Extract parameter descriptions from docstring :param name: text lines."""
    doc = func.__doc__ or ""
    descriptions: dict[str, str] = {}
    for match in re.finditer(r":param\s+(\w+)\s*:\s*(.+?)(?:\n|$)", doc):
        descriptions[match.group(1)] = match.group(2).strip()
    return descriptions


def _build_json_schema(func: Callable) -> dict:
    sig = inspect.signature(func)
    param_descs = _parse_param_descriptions(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        py_type = str if param.annotation is inspect.Parameter.empty else param.annotation
        json_type = _TYPE_MAP.get(py_type, "string")

        prop: dict = {"type": json_type}
        if name in param_descs:
            prop["description"] = param_descs[name]
        if param.default is not inspect.Parameter.empty:
            if isinstance(param.default, str):
                prop["default"] = param.default
            elif isinstance(param.default, (int, float, bool)):
                prop["default"] = param.default
        else:
            required.append(name)

        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
