# Tools — Tool Layer

## Role

The muscle layer. Tools are pure functions that perform actual operations (network requests, encoding, scanning). They are registered in a central registry and exposed to Workers as LLM function-calling definitions.

## Dual-Layer Architecture

| Layer | Scope | Examples |
|---|---|---|
| **Shared Utilities** | Available to ALL Workers | encoding, network |
| **Domain Weapons** | Available only to matching domain Worker | web_recon, web_exploit, crypto, reverse |

## Files

| File | Role | Input | Output |
|---|---|---|---|
| `__init__.py` | **CRITICAL** — imports all tool modules so `@register_tool` decorators fire | — | — |
| `registry.py` | Central tool registry with decorator-based registration | — | ToolDef list for LLM function calling |
| `shared/encoding.py` | Encode/decode utilities | String + format | Transformed string |
| `shared/network.py` | Basic HTTP and socket operations | URL + params | Response dict |
| `web/recon.py` | Web reconnaissance tools | URL + options | Scan results dict |
| `web/exploit.py` | Web exploitation tools | URL + payload params | Exploit result dict |

## Tool Registration

```python
from tools.registry import register_tool, ToolDef

@register_tool(
    category="web",
    name="web_directory_scan",
    description="Brute-force scan directories on a target URL using a wordlist"
)
def web_directory_scan(url: str, wordlist: str = "common") -> dict:
    ...
```

The registry auto-generates JSON Schema for function calling from type hints.

## Adding a New Tool

1. Define a function with type hints
2. Add `@register_tool(category="...")` decorator
3. Place in appropriate `tools/<category>/` directory
4. Import in `tools/<category>/__init__.py`
