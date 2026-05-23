"""Lightweight event hook system for CTFAgent.

Allows external modules (Filter, Guardrail, logging, notifications)
to intercept engine events without modifying engine.py.

Usage:
    from hooks import on

    @on("before_execute")
    def my_guardrail(event):
        if dangerous(event.task):
            event.block("reason")

    @on("after_execute")
    def my_filter(event):
        event.result["findings"] = clean(event.result["findings"])
"""

from typing import Callable, Any


class HookEvent:
    """A named event with mutable payload. Callbacks can read and modify data."""

    __slots__ = ("name", "data", "_blocked", "_block_reason")

    def __init__(self, name: str, data: dict[str, Any] | None = None):
        self.name = name
        self.data = data or {}
        self._blocked = False
        self._block_reason = ""

    def block(self, reason: str = "") -> None:
        self._blocked = True
        self._block_reason = reason

    @property
    def blocked(self) -> bool:
        return self._blocked

    @property
    def block_reason(self) -> str:
        return self._block_reason


class HookRegistry:
    """Singleton registry mapping event names to lists of callbacks."""

    _instance: "HookRegistry | None" = None

    def __new__(cls) -> "HookRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._hooks: dict[str, list[Callable]] = {}
        return cls._instance

    def register(self, event_name: str, callback: Callable) -> None:
        self._hooks.setdefault(event_name, []).append(callback)

    def unregister(self, event_name: str, callback: Callable) -> None:
        if event_name in self._hooks:
            self._hooks[event_name] = [
                cb for cb in self._hooks[event_name] if cb is not callback
            ]

    def fire(self, event_name: str, **data) -> HookEvent:
        """Fire an event. Returns the event object so caller can check .blocked.

        Each callback receives the HookEvent and can:
        - Read/modify event.data
        - Call event.block(reason) to stop execution
        """
        event = HookEvent(event_name, data)
        for cb in self._hooks.get(event_name, []):
            try:
                cb(event)
            except Exception as exc:
                print(f"[Hook Warn] {event_name}: {cb.__name__} raised {exc}")
            if event.blocked:
                break
        return event

    def clear(self) -> None:
        self._hooks.clear()


# Module-level convenience
_registry = HookRegistry()


def on(event_name: str):
    """Decorator: register a function as a hook callback.

    @on("after_execute")
    def my_filter(event): ...
    """
    def decorator(fn: Callable) -> Callable:
        _registry.register(event_name, fn)
        return fn
    return decorator


def fire(event_name: str, **data) -> HookEvent:
    return _registry.fire(event_name, **data)


def get_registry() -> HookRegistry:
    return _registry
