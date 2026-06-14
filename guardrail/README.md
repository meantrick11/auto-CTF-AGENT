# Guardrail — DEPRECATED

**This module has been merged into `supervisor/`.**
Safety logic now lives in `supervisor/safety.py`.

See: `supervisor/README.md`

Inspired by Claude Code: deny-first permission model, multiple independent safety layers, any layer can block.

## Hook Points (3 layers)

```
User Goal
    │
┌───▼────── [1] before_plan        ← 目标级别检查
│   └─ Goal 合法吗？目标在白名单吗？
│
├─ Commander.plan()
│
┌───▼────── [2] before_task_create ← 任务级别检查
│   └─ Task 类型允许吗？参数安全吗？
│
└─ 写 Task 到黑板
    │
┌───▼────── [3] before_execute     ← 执行级别检查（最后一道防线）
│   └─ URL 是内网吗？端口限制？重试次数？
│
└─ Worker.execute()
```

## Input/Output

All three hooks receive the same pattern:

**Input (event.data):**
```python
# before_plan
{"snapshot": {...}, "round": int}

# before_task_create
{"task_def": {"type": "web_recon", "instruction": "...", "input_data": {...}}}

# before_execute
{"task": {...}, "worker_name": "web_worker"}
```

**Block:** `event.block("reason")` — engine checks `event.blocked` and stops execution at that point.
**Pass:** do nothing, engine continues normally.

## Rule Model (Deny-First)

```python
# Rules evaluated in order. First match wins.
rules = [
    # ── Deny rules (hard blocks) ──
    {"type": "deny", "match": {"target_host": "*.gov.cn"}, "reason": "政府域名禁止攻击"},
    {"type": "deny", "match": {"target_host": "!192.168.*"}, "reason": "仅允许本地/测试网络"},
    {"type": "deny", "match": {"target_host": "!127.0.0.1"}, "reason": "仅允许本地/测试网络"},
    {"type": "deny", "match": {"task_type": "web_exploit", "target_host": "!localhost"}, "reason": "漏洞利用仅允许本地目标"},

    # ── Require confirm rules (prompt user) ──
    {"type": "confirm", "match": {"task_type": "web_exploit"}, "reason": "漏洞利用需要人工确认"},

    # ── Allow rules (pass through) ──
    {"type": "allow", "match": {"task_type": "web_recon"}, "reason": "侦察操作默认允许"},
]

# Default: deny if no rule matches
default_action = "deny"
```

## Implementation Skeleton

```python
# guardrail/rules.py
from dataclasses import dataclass
from hooks import on

@dataclass
class Rule:
    action: str        # "deny" | "allow" | "confirm"
    match: dict        # conditions: target_host, task_type, port, etc.
    reason: str

class Guardrail:
    def __init__(self, rules: list[Rule], default: str = "deny"):
        self.rules = rules
        self.default = default

    def check(self, context: dict) -> tuple[bool, str]:
        """Returns (allowed, reason)."""
        for rule in self.rules:
            if self._matches(rule, context):
                if rule.action == "deny":
                    return False, rule.reason
                if rule.action == "allow":
                    return True, ""
        return self.default != "deny", "No matching allow rule"

    def _matches(self, rule, ctx) -> bool:
        # Check each condition in rule.match against context
        ...

# ── Register hooks ──

guard = Guardrail(rules=load_rules_from_config())

@on("before_task_create")
def check_task(event):
    task_def = event.data["task_def"]
    ctx = {
        "task_type": task_def["type"],
        "target_host": extract_host(task_def.get("input_data", {})),
    }
    allowed, reason = guard.check(ctx)
    if not allowed:
        event.block(reason)

@on("before_execute")
def check_execute(event):
    task = event.data["task"]
    ctx = {"task_type": task["type"], "target_host": extract_host(task.get("input_data", {}))}
    allowed, reason = guard.check(ctx)
    if not allowed:
        event.block(reason)
```

## Testing Guardrail Independently

No engine needed. Test rules against context dicts:

```python
from guardrail.rules import Guardrail, Rule

rules = [
    Rule("deny", {"target_host": "*.gov.cn"}, "禁止政府域名"),
    Rule("allow", {"task_type": "web_recon"}, "侦察允许"),
]
guard = Guardrail(rules)

# Should pass
assert guard.check({"task_type": "web_recon", "target_host": "localhost"})[0] is True

# Should deny
assert guard.check({"task_type": "web_recon", "target_host": "xxx.gov.cn"})[0] is False
```
