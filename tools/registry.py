"""Central tool registry — decorator-based registration + JSON Schema generation."""

from dataclasses import dataclass, field
from typing import Callable, Any, Optional
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
    type(None): "null",
}


def _resolve_type(py_type) -> str | None:
    """Resolve a Python type annotation to a JSON Schema type.

    Handles union types like dict|None → 'object', str|None → 'string',
    and Optional[X] / Union[X, None].
    Uses typing.get_origin/get_args for reliable access across Python versions.
    """
    import typing as _typing
    origin = _typing.get_origin(py_type)
    if origin is not None:
        args = _typing.get_args(py_type)
        # Check if it's a Union type (Optional[X] or X | None)
        import types as _types
        if origin in (_types.UnionType, _typing.Union):
            for arg in args:
                if arg is not type(None):
                    return _TYPE_MAP.get(arg)
            return None
        # Handle list[X], dict[K,V] etc.
        if origin in (list, dict):
            return _TYPE_MAP.get(origin)
    return _TYPE_MAP.get(py_type)


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
        json_type = _resolve_type(py_type) or "string"

        # Check if this param is optional (has default or is Optional[...])
        has_default = param.default is not inspect.Parameter.empty
        is_optional = has_default  # has default → optional
        # Also detect Optional[X] = X | None or typing.Optional[X]
        import types as _types
        import typing as _typing
        origin = _typing.get_origin(py_type)
        if origin in (_types.UnionType, _typing.Union):
            args = _typing.get_args(py_type)
            if type(None) in args:
                is_optional = True

        prop: dict = {"type": json_type}
        if name in param_descs:
            prop["description"] = param_descs[name]
        if param.default is not inspect.Parameter.empty:
            if isinstance(param.default, str):
                prop["default"] = param.default
            elif isinstance(param.default, (int, float, bool)):
                prop["default"] = param.default

        if not is_optional:
            required.append(name)

        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
