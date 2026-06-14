# CTFAgent — LLM-Driven Multi-Agent Penetration Testing System

## Project State (2026-05-24)

**MVP phase complete. Context compression implemented.**

### What Works (end-to-end verified)
- Base64 decode → flag extraction (2 rounds, 1 finding, flag captured)
- HTTP target attack → recon + exploit → flag (2 rounds, 10 findings, flag captured)
- **LLM retry** — exponential backoff (1s/2s/4s) on transient API errors (429, 5xx, connection)
- **Config validation** — fail-fast at startup if API key missing or base_url misconfigured
- **Filter** — rule-based data washer: dedup by (type,title), normalize, mark large data
- **Compaction** — LLM summarization of findings when data exceeds 3000-char threshold
- **Commander compressed view** — gets summary + recent 5 findings + stats, not full dump

### Current Capabilities
- Web reconnaissance: directory scan, form extraction, header analysis
- Web exploitation: SQLi, XSS, command injection probing
- Encoding tools: base64, hex, URL encode/decode, ROT13
- HTTP GET/POST with SSL verification disabled (Windows compat)
- Context compression: two-tier (Filter rules → Compactor LLM) to keep Commander context small

### Deferred (explicitly excluded from MVP)
- Guardrail (Safety sentinel) — no dangerous ops in local testing
- Multi-domain workers (Crypto, RE, PWN, Forensics) — only Web
- DB persistence — JSON file only
- Concurrency — serial loop
- MCP tool integration — tools are hardcoded Python functions
- RAG / knowledge base — no persistent learning across tasks
- Cross-task memory — blackboard cleared between runs

## Hook System (7 event points)

All future modules (Filter, Guardrail, logging, notifications) plug into engine via hooks. **Zero engine modifications needed.**

```
before_plan        → Guardrail: check goal safety
after_plan         → Logging: record Commander decisions
before_task_create → Guardrail: check task safety
before_execute     → Guardrail: last safety gate
after_execute      → Filter: dedup/normalize/mark (implemented)
on_finding         → Notify: flag found → alert
on_complete        → Cleanup: save report, notify
```

Usage: `from hooks import on` then `@on("after_execute")` on a function that takes an `event` object.
Call `event.block("reason")` to stop execution. Modify `event.data` to mutate payload (Filter pattern).

Key files: `hooks.py` (HookEvent + HookRegistry), `orchestrator/engine.py` (7 fire points).

## Architecture (v2 — 9 modules + Supervisor Agent)

```
main.py → orchestrator/engine.py  ←── the ONLY coupling point
              ├── commander/agent.py           (depends: config, utils, blackboard.schema)
              ├── workers/registry.py          (depends: workers/base_worker.py)
              ├── workers/web/agent.py         (depends: config, utils, tools, base_worker)
              ├── supervisor/                  (NEW — safety + drift + quality + maintenance. Consumes guardrail/ + filter/ + evaluator/)
              ├── blackboard/                  (depends: NOTHING — pure storage)
              └── tools/                       (depends: registry.py)
```

**Key rule:** Three agents — Commander (brain), Worker (muscle), Supervisor (immune system).
Commander and Worker are 100% independent. Supervisor monitors both via hooks.
All coordination through Blackboard: Commander writes Directions → Workers write Findings → Supervisor writes Observer Notes.

### Module Responsibility Principle

**Each module does ONE thing well:**

| Module | One Thing |
|---|---|
| Commander | Read state → decide attack directions |
| Worker | Execute one direction → return findings |
| Supervisor | Monitor Commander+Worker: safety, drift, quality, maintenance. Layer 1 (rules) + Layer 2 (Agent) |
| Blackboard | Store and serve state — information exchange + short-term memory |
| Engine | Drive the loop (sole coupling point) |
| ToolRegistry | Register and dispatch tools |
| WorkerRegistry | Register and route workers |
| Hooks | Fire events, let plugins intercept |

## File Index

### Entry & Config
| File | Role |
|---|---|
| `main.py` | CLI entry: argparse → Engine.run() |
| `config.py` | Loads .env, creates OpenAI client (DeepSeek), SSL config, validate_config() |
| `requirements.txt` | openai>=1.0.0, python-dotenv>=1.0.0 |
| `.env.example` | API key template |
| `.env` | Actual keys (git-ignored) |

### Blackboard (State Plane)
| File | Role |
|---|---|
| `blackboard/schema.py` | Data models: Goal, Task, Finding, EventLog + enums |
| `blackboard/blackboard.py` | CRUD + JSON atomic write + compaction + commander_view. Auto-clears between runs. |

### Orchestrator
| File | Role |
|---|---|
| `orchestrator/engine.py` | Main loop: Commander.plan → Worker.execute → compact → converge. Clears old blackboard on start. |

### Commander (Orchestration Plane)
| File | Role |
|---|---|
| `commander/agent.py` | Reads compressed commander_view → LLM → returns decision JSON. NO tools. |
| `commander/prompts/system_prompt.txt` | Forbids self-solving, requires delegation to workers. |

### Workers (Action Plane)
| File | Role |
|---|---|
| `workers/registry.py` | Singleton WorkerRegistry. Prefix-based routing: `route("web_recon")` → WebWorker. Same pattern as ToolRegistry. |
| `workers/base_worker.py` | Abstract base class + **TaskResult** + **WorkerFinding** dataclasses. Enforces Worker return schema. |
| `workers/web/agent.py` | WebWorker: LLM + OpenAI tool-calling loop (max 8 iter). Returns **TaskResult** (not raw dict). |
| `workers/web/prompts/system_prompt.txt` | Web security specialist persona. CRITICAL: output ONLY JSON. |

### Tools
| File | Role |
|---|---|
| `tools/registry.py` | Singleton ToolRegistry. @register_tool decorator. Auto-generates JSON Schema for function calling. |
| `tools/shared/encoding.py` | base64_encode/decode, hex_encode/decode, url_encode/decode, rot13 |
| `tools/shared/network.py` | http_get, http_post (urllib, SSL verify disabled) |
| `tools/web/recon.py` | web_directory_scan, web_extract_forms, web_analyze_headers |
| `tools/web/exploit.py` | web_sqli_test, web_xss_test, web_command_injection_test |

### Supervisor (Immune System — converged guardrail + filter + evaluator + maintenance)
| File | Role |
|---|---|
| `supervisor/__init__.py` | Registers all 7 hooks, redirection system (block dead-end task types), wires Layer 1 → Layer 2 escalation |
| `supervisor/safety.py` | Layer 1: Task/instruction safety checks (formerly guardrail/) |
| `supervisor/quality.py` | Layer 1: Finding dedup/normalize/validate (formerly filter/) |
| `supervisor/drift.py` | Layer 1: Stagnation/repetition/stuck detection (formerly evaluator/) |
| `supervisor/maintenance.py` | Layer 1: Compaction triggering + observer notes |
| `supervisor/agent.py` | Layer 2: SupervisorAgent — LLM semantic review (called only when Layer 1 flags suspicious) |
| `supervisor/prompts/system_prompt.txt` | Supervisor Agent system prompt |
| `supervisor/README.md` | Module docs |

### Deprecated (merged into supervisor/)
| File | Role |
|---|---|
| `filter/` | → supervisor/quality.py |
| `guardrail/` | → supervisor/safety.py |

### Docs
| File | Role |
|---|---|
| `PROGRESS.md` | Daily progress log — what was done each day, brief |
| `docs/SPEC.md` | **Architecture spec + Worker paradigm** — component contracts, info flow, template for new workers, architecture rules |
| `docs/architecture.md` | Architecture overview (simplified) |
| `ArchitectureBookEN.md` | Full architecture design document (the blueprint) |
| `ArchitectureBookCN.md` | Chinese version |

### Challenge (local test range — staged by difficulty)
| File | Role |
|---|---|
| `challenge/README.md` | Challenge catalog: stage list, vulnerability matrix, attack chains, run instructions |
| `challenge/stage1_basic/test_target.py` | CTF Corp Portal — 14 endpoints, multi-step CTF (SQLi, XSS, CI, info leak, auth bypass) |
| `challenge/stage2_supervisor/test_supervisor.py` | Supervisor validation — traps (fake SQLi), dead ends, correct path (register → token → flag) |

### Hook System
| File | Role |
|---|---|
| `hooks.py` | HookEvent + HookRegistry. `@on("event")` decorator, `fire("event", **data)`, `event.block()`. Singleton. |

### Utilities
| File | Role |
|---|---|
| `utils.py` | `extract_json()` bracket-counting JSON extractor + `retry_llm_call()` exponential backoff retry |

## Virtual Environment (MANDATORY)

**ALL Python operations MUST run inside `.venv`.** This includes `python`, `pip install`, `pytest`, and any other Python commands.

```powershell
# Activate (PowerShell) — do this FIRST in every terminal
.\.venv\Scripts\Activate.ps1

# If blocked by execution policy (one-time fix, Run as Administrator):
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Rules:
- **Never run `pip install` globally** — always activate venv first
- **Never use `pip3`** on Windows — use `pip` (venv's pip)
- **Check prompt shows `(.venv)`** before running anything
- **When adding dependencies**: `pip install <pkg> && pip freeze > requirements.txt` to keep lock file updated

## How to Run

```powershell
# One-time setup
.\.venv\Scripts\Activate.ps1
cp .env.example .env   # then edit .env with real DeepSeek key
pip install -r requirements.txt

# Simple test (no target needed)
python main.py -g "Decode this base64: ZmxhZ3tmYWpka2xmamFvZmpxZWlmXzEzMjE0YWZsZmFpb30=" -n 5

# Full attack (needs target)
# Terminal 1: python challenge\stage1_basic\test_target.py
# Terminal 2: python main.py -g "Attack http://localhost:8888 and capture the flag" -n 8
```

## Key Design Decisions

1. **Each module does ONE thing well** — Commander decides, Worker executes, Blackboard stores, Filter cleans, Compactor summarizes, Engine wires. No module does two jobs.
2. **SSL verify disabled** (CTFAGENT_SSL_VERIFY=false in .env) — Windows certificate chain issue
3. **Blackboard auto-clears** each run — `engine.py` deletes old JSON before creating new Blackboard
4. **Findings are append-only** — never modified after write. Compaction writes to a separate `situation_summary` field, leaving original findings intact.
5. **Two views from Blackboard**: `snapshot()` (full, for Workers who need detail) and `get_commander_view()` (compressed, for Commander who needs overview)
6. **Context compression is two-tier**: Filter (rules, per-task, free) → Compactor (LLM, cross-round, threshold-triggered)
7. **Tool registration** happens on import — `tools/__init__.py` imports all tool modules so @register_tool decorators fire
8. **DeepSeek API** via OpenAI SDK — base_url is `https://api.deepseek.com` (no /v1 needed)
9. **extract_json()** uses bracket counting, not regex — handles nested arrays/objects correctly
10. **LLM retry** on transient failures — 3 attempts with exponential backoff, does not retry on auth errors

## Coding Conventions & Hard-Won Rules

These were discovered through debugging. Violating any of them breaks the system.

### Agent Rules (system prompt enforced)
- **Commander MUST delegate.** Prompt says "FORBIDDEN from solving problems yourself." Even trivial base64 decode must be a task. "Round 1: ALWAYS create at least 1 task. Never declare completed in round 1."
- **Worker MUST output ONLY JSON.** Prompt says "CRITICAL: Output ONLY the JSON object. Do NOT add any text before or after it." No markdown wrapping, no conversational text.
- **Commander uses `response_format={"type": "json_object"}`** — DeepSeek supports this, makes parsing reliable.

### JSON Parsing
- **Use `utils.extract_json()` for ALL LLM output parsing.** Never use regex — nested arrays/objects in findings data will break it.
- `extract_json()` uses bracket counting with string-literal awareness (handles `\"` and `\\` inside strings).
- Both Commander (`_parse_output`) and Worker (`_parse_final_output`) use it.

### Blackboard
- **Delete old JSON BEFORE constructing Blackboard** in `engine.run()`. If you construct first, `_load()` reads old data into memory, then deleting the file does nothing.
- **Enum deserialization** in `_load()`: JSON stores strings like `"flag"`, but schema expects `FindingType.FLAG`. Must convert string→enum before creating dataclass objects. Same for GoalStatus and TaskStatus.
- **Atomic write**: temp file + `os.replace()` to avoid corruption on crash.

### Tool System
- **`tools/__init__.py` must import all tool modules.** The `@register_tool` decorator fires on import. Without the imports, tools exist in code but not in the registry.
- Tool registration is a **singleton**. `get_registry()` always returns the same instance.
- Tools are **pure functions** with type hints. The registry auto-generates JSON Schema from `inspect.signature()`.
- Domain tools MAY import shared tools (e.g., `tools/web/recon.py` imports `http_get` from shared network).
- **Type annotation introspection: use `typing.get_origin()` and `typing.get_args()`.** Never use direct `__origin__`/`__args__` attribute access on type annotations — `types.UnionType` (from `X | None` syntax) stores these differently and direct access returns None. This cost us hours debugging why `dict | None` was resolving to `"string"` in tool schemas.

### API / LLM
- **DeepSeek base URL is `https://api.deepseek.com`** (no `/v1` suffix). The OpenAI SDK appends `/chat/completions` automatically.
- **SSL verify is OFF** (`CTFAGENT_SSL_VERIFY=false`). Windows cert chain issues. Config creates `httpx.Client(verify=False)`.
- **`config.create_client()`** is the single factory for OpenAI clients. Both Commander and Worker use it.
- Worker tool calling uses **OpenAI format**: `tool_calls` in assistant messages, `role: "tool"` for results.
- Agent loop has **max 5 iterations**, forced output at iteration 4 (removes tools, demands JSON). Prevents loop exhaustion.

### Agent Independence
- **Commander and Worker have ZERO imports of each other.** Verified by grep.
- Commander's `plan()` input/output are plain dicts — no Blackboard/Task objects. This keeps it testable in isolation.
- Worker's `execute()` input is a task dict + snapshot dict — no Commander objects. Returns `TaskResult` (standard contract).
- **Only `orchestrator/engine.py` imports both Commander and Worker.** It is the sole coupling point.
- `workers/registry.py` is imported by both `engine.py` and `workers/__init__.py` — it's infrastructure, not coupling.

### Error Handling
- Both `Commander.plan()` and `Worker.execute()` have try/except that return structured results (never raise).
- Worker returns `TaskResult(status="failed", summary="...", findings=[])` on error so the loop continues.
- `retry_llm_call()` in `utils.py` wraps all LLM API calls. Retries on 429/5xx/connection/timeout. Does NOT retry on 401/400.

### Context Compression
- **Filter is rule-based, never drops data.** Dedup merges (type,title), normalize fills missing fields, truncate only marks (`_truncated=True`). No confidence-based deletion.
- **Compactor is LLM-based, threshold-triggered.** Only runs when findings data exceeds 3000 chars. Generates `situation_summary` dict stored separately from original findings.
- **Findings are append-only.** Once written to blackboard, findings are never modified. Compaction writes to a separate field.
- **Commander reads `get_commander_view()`** (summary + recent 5 findings + stats), not raw `snapshot()`.
- **Worker reads `snapshot()`** (full findings) — Workers need detail to do their job.
- **Compaction is non-critical.** If it fails, Commander gets a larger view but execution continues.

### Worker Contract (schema + registration)
- **ALL `Worker.execute()` methods MUST return `TaskResult`.** This is the Action Plane contract. Filter, Blackboard, and Engine depend on `.status`, `.summary`, `.output_data`, `.findings` being present.
- `TaskResult.from_dict(d)` bridges raw LLM JSON → structured object. `to_dict()` bridges back. Use `from_dict` when parsing LLM output, `to_dict` when persistence needs it.
- `WorkerFinding` is the raw finding from a Worker (no id/timestamp). Engine enriches it into `blackboard.schema.Finding` when writing to blackboard.
- **Worker registration is explicit** in `engine.__init__()`: `get_worker_registry().register(worker, name=..., domain=..., task_prefixes=[...])`. The `task_prefixes` list defines routing — e.g. `["web_"]` means any task type starting with `web_` routes to this worker.
- Engine's `_route_task()` calls `registry.route(task_type)` with fallback to `web_worker`. No hardcoded if/elif chains.
- `WorkerRegistry` is a singleton (same pattern as `ToolRegistry`). Adding a new Worker = one `register()` call in Engine init + one domain tool import.

### File Organization
- Each module has a `README.md` documenting: role, files, input/output protocols.
- System prompts live in `prompts/` subdirectories, loaded at runtime (not hardcoded).
- `__init__.py` files export public API of each module.

### Session Discipline (MANDATORY)

1. **After every confirmed change, update the corresponding records or README files.** Never leave documentation stale after code changes. See the Documentation Discipline table below for the specific update rules.
2. **Before modifying a module: if the implementation approach is uncertain, or it's unclear whether something should be reserved for future use, ask the user first and wait for instructions.** Do NOT assume, fantasize, or make unilateral decisions (including but not limited to: committing code, deleting files, changing architecture conventions). Ask first, then act.

### Documentation Discipline (MANDATORY after every change)

| When you... | You MUST update... |
|---|---|
| Add/remove a file in a module | That module's `README.md` — file listing and roles |
| Add a new tool | `tools/README.md` — add to tool table |
| Change a module's interface/contract | That module's `README.md` + `docs/SPEC.md` if it's a core contract |
| Fix a tricky bug or discover a new rule | `CLAUDE.md` — add to Coding Conventions so it never repeats |
| Complete a work session | `PROGRESS.md` — date, what was done, why |
| Change Commander/Worker behavior | Respective `prompts/system_prompt.txt` if prompt needs updating |
| Add a new module | Create its `README.md` (following existing format) + add to this file index |

**Why:** Code tells you what it does, but README tells you WHY and HOW to use it. Stale docs are worse than no docs — they actively mislead.

## Adding a New Worker (future reference)

1. `workers/<domain>/agent.py` — extend BaseWorker, implement `execute() → TaskResult`
2. `workers/<domain>/prompts/system_prompt.txt` — domain-specific system prompt
3. `tools/<domain>/` — register tools with `@register_tool`
4. In `orchestrator/engine.py` `__init__` add one line:
   ```python
   reg.register(CryptoWorker(model=model), name="crypto_worker",
                domain="crypto", task_prefixes=["crypto_"])
   ```
5. In `workers/__init__.py` add the new Worker class export
6. Commander needs NO changes (task routing is prefix-based, Commander just generates task types)

## Next Steps (user's priority order TBD)

- Tool deepening: SQLi/CI exploit chains (beyond detection → exploitation)
- Additional domain workers (Crypto, RE)
- Add persistent memory / RAG knowledge base
- MCP tool integration
- SQLite persistence
- Worker context compression (Worker currently gets full snapshot — same approach as Commander)
