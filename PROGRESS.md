# CTFAgent — Daily Progress

## 2026-05-23 — MVP Complete

- Core loop: Commander → Blackboard → Worker → loop, end-to-end verified
- 15 registered tools (encoding, network, web recon/exploit)
- targets/test_target.py: local vulnerable HTTP server
- DeepSeek API via OpenAI SDK
- Base64 decode scenario: 2 rounds, flag captured
- HTTP attack scenario: 2 rounds, 10 findings, flag captured
- TaskResult + WorkerFinding enforced schema
- WorkerRegistry prefix-based routing
- Hook system with 7 event points

## 2026-05-24 (afternoon) — Failure Transparency + Worker Paradigm

- **error_detail in TaskResult**: Worker failures now report structured error (error_type, detail), not just "failed"
- **Commander sees recent_tasks**: get_commander_view() includes task history with errors → Commander avoids repeating dead ends
- **Compact includes failed tasks**: dead_ends field in summary
- **Confidence boost on duplicates**: same (type,title) from multiple tasks → confidence += 0.15, confirmed_by counter
- **PROGRESS.md**: daily progress log
- **docs/SPEC.md**: architecture spec + Worker paradigm template + information flow diagram

## 2026-05-24 (morning) — Stability + Context Compression

### Infrastructure hardening
- **LLM retry**: `utils.retry_llm_call()` — exponential backoff on 429/5xx/connection/timeout
- **Config validation**: `config.validate_config()` — fail-fast at startup
- **DeepSeek API URL fix**: changed default from `api.deepseek.com/v1` → `api.deepseek.com`

### Context compression (two-tier)
- **Filter**: rule-based, hooks into `after_execute`. Dedup + normalize + mark large data. Never drops.
- **Compactor**: `Blackboard.compact()` — LLM summarization when findings exceed 3000-char threshold
- **Commander compressed view**: `get_commander_view()` — summary + recent 5 findings + stats
- **Worker full view**: `snapshot()` — still gets all data (needs detail)

### Information flow improvements
- **Failure transparency**: `TaskResult.error_detail` — structured error (error_type, detail). Commander sees WHY tasks failed, not just "failed".
- **Recent tasks in Commander view**: Commander can see completed + failed task history, avoids repeating dead ends.
- **Compact includes failed tasks**: compactor prompt notes what NOT to retry.
- **Cross-task dedup**: `add_finding()` on duplicate (type,title) → boosts confidence + confirmed_by counter, doesn't skip.

### Network tools fixed
- **http_post**: disabled auto-redirect (was swallowing Set-Cookie headers)
- **http_get/http_post**: added `cookies` parameter
- Root cause of all login failures in earlier test runs

### Test target upgraded
- `targets/test_target.py`: 14 endpoints, multi-step CTF (not one-shot flag)
- Flag only in `/admin` (requires login chain)
- Tested end-to-end: 7 rounds, 14 findings, flag captured

### Documentation
- Module responsibility principle: "each module does ONE thing well"
- READMEs updated: filter/, blackboard/, orchestrator/, commander/
- CLAUDE.md synced with current state

## 2026-06-06 — Documentation Pass + File Reorganization

### File reorganization
- **test_target.py moved**: root → `targets/test_target.py` (cleaner project root)
- **targets/README.md**: target catalog with vulnerability matrix, attack chain docs, how to add new targets

### Code documentation
- **orchestrator/engine.py**: full inline comments (Chinese) on every phase — hook fire points, blackboard ops, task routing, flag extraction, compaction trigger
- **main.py**: inline comments on config validation, output file logic
- **config.py**: inline comments on SSL_VERIFY bool conversion (str→bool via `not in`)

### CLAUDE.md hardening
- **Virtual Environment section**: mandatory venv rules, activation commands, execution policy fix
- **Documentation Discipline table**: which files to update when (PROGRESS, README, SPEC, CLAUDE, prompts)
- **File index updated**: test_target.py → targets/test_target.py, targets/README.md added

### README accuracy pass
- **README.md**: all test_target.py paths updated, targets/ directory added to tree
- **tools/README.md**: `__init__.py` added to file table (critical — imports trigger @register_tool)
- **workers/web/README.md**: `web_command_injection_test` added to tool list (was missing)

## 2026-06-06 — Bug Fixes (architecture review findings)

### High priority
- **http_post Content-Type**: fixed duplicate header — now checks if user headers already contain Content-Type before adding default `x-www-form-urlencoded`. Fixes inability to send JSON POST.
- **Exploit payloads untruncated**: removed hardcoded `[:8]` / `[:6]` / `[:6]` slices on SQLi (14), XSS (8), CI (10) payload lists. Full coverage.
- **Encoding binary safety**: `base64_decode` and `hex_decode` now catch `UnicodeDecodeError` and return hex fallback instead of crashing on binary data.
- **JSON Schema descriptions**: `_build_json_schema` now parses `:param name: description` from function docstrings and injects them into parameter schemas for LLM function calling.

### Medium priority
- **Network error distinction**: replaced bare `except Exception` with specific `URLError` / `socket.timeout` / `Exception` branches. Error dicts now include `error_type` field (connection_error / timeout / unknown).
- **Compactor retry**: wrapped `compact()` LLM API call with `utils.retry_llm_call()` for consistency with Commander and Worker.

### Low priority
- **Stale docs fixed**: `docs/architecture.md` and `ArchitectureBookEN.md` updated to reflect Filter is implemented (was incorrectly marked as deferred).
- **__pycache__ already gitignored**: `.gitignore` already had `__pycache__/` — no change needed.

## 2026-06-06 — Communication protocol hardening

### Decision dataclass — Commander output typed
- Added `Decision` dataclass to `blackboard/schema.py` with `from_llm_output()` validator
- Validates `decision` field is one of: `continue` | `completed` | `failed` — raises `ValueError` on bad input
- `Commander.plan()` now returns `Decision` instead of raw dict
- `_parse_output()` wraps LLM output with `Decision.from_llm_output()` — parse failures explicitly reported

### Engine enforces contracts
- Engine accesses `decision.decision` / `decision.reasoning` / `decision.new_tasks` / `decision.final_summary` (attributes, not `.get()`)
- Removed `isinstance(result, TaskResult) else dict` fallback — Engine now requires TaskResult
- Removed `isinstance(result, TaskResult)` guard on error_detail — always TaskResult now

### TaskResult + WorkerFinding moved to canonical location
- Moved `TaskResult` and `WorkerFinding` from `workers/base_worker.py` → `blackboard/schema.py`
- `blackboard/schema.py` now the single source of truth for ALL system data types
- `workers/base_worker.py` imports + re-exports for backward compat
- Updated imports in: engine.py, workers/__init__.py, workers/web/agent.py, filter/cleaner.py, docs/SPEC.md

## 2026-06-06 — Architecture redesign (v2)

### Research: BreachWeave reference analysis
- Studied BreachWeave (Tencent hackathon 1st place / 613 teams) — Manager/Solver/Observer architecture
- Key takeaways: Observer for drift detection, Idea vs Memory separation, multi-Solver parallel, structured compaction, stability-first scheduling

### Architecture v2 design
**Engine**: drives loop, parallel dispatch by direction (not serial by task)
**Commander**: allocates attack directions (not individual tasks), can output "hold"
**Worker**: same-domain multiple instances, each with different attack direction, stateless
**Blackboard**: pure information exchange + short-term memory. No compression, no judgment.
**Context Manager**: information quality — Phase 1 Filter (rules) + Phase 2 Compact (LLM, structured PRESERVE/DISCARD)
**Evaluator**: strategy assessment — drift detection, dead-end marking, writes observer_notes to Blackboard for Commander
**Monitor**: cross-cutting metrics — tokens, timing, success rate. Read-only.
**Memory**: cross-run persistent knowledge (RAG) — deferred

### Architecture docs updated
- `docs/SPEC.md` — fully rewritten with v2 module contracts, data flow, types, rules
- `docs/architecture.md` — rewritten overview with module table, directory map, MVP/v2/deferred status
- `CLAUDE.md` — to be updated with new file index (pending, session running late)

## 2026-06-14 — Supervisor Agent + Architecture Hardening

### BUUCTF live test results
- Ran against real BUUCTF target (10 rounds) — flag not captured
- Root cause analysis: Commander hallucination + Worker 8-iteration loop exhaustion + no supervision
- Commander prompt fix eliminated hallucinations (no more "Burp Suite" instructions)

### Supervisor module implemented
- **Converged guardrail + filter + evaluator + maintenance into `supervisor/`**
- Layer 1 (rules): safety.py, quality.py, drift.py, maintenance.py — pure Python, zero LLM
- Layer 2 (agent): SupervisorAgent — LLM semantic review, called only when rules flag suspicious
- Registered on all 7 hook points: before_plan, after_plan, before_task_create, before_execute, after_execute, on_finding, on_complete
- Commander now receives observer_notes in every round's blackboard view
- Commander prompt updated: decodes observer_notes, tool catalog injected, hallucinations blocked
- filter/ and guardrail/ modules deprecated → logic moved to supervisor/

### Engine updates
- `import supervisor` replaces `import filter.cleaner`
- `init_supervisor()` called at mission start to reset drift tracker
- `supervisor_should_compact()` replaces blackboard._needs_compact()
- observer_notes injected into Commander view before each plan() call

### Architecture evolved: 3-Agent design
```
Commander (brain) → Worker (muscle) → Blackboard (memory)
                 ↘ Supervisor (immune system) ↗
                   monitors both, writes observer_notes
```

### To do next
1. Tool deepening: http_request merge, SQLi exploit chain, CI exploit chain
2. More domain workers (Crypto, RE)
3. Persistent memory / RAG knowledge base

## 2026-06-14 — Supervisor Redirection + Worker Reliability Fixes

### Redirection system (user-requested active intervention)
- Refactored `supervisor/__init__.py` to implement **redirection**: stronger than observer_notes
- `set_redirection(blocked_types, suggested, reason)` — blocks specific task types
- `clear_redirection()` — when task succeeds with substantial findings
- `_is_blocked_by_redirection(task_def)` — enforced in before_task_create hook
- `_analyze_and_intervene()` — reads Worker tool_trace, detects stuck (>=5 same-tool errors or >=70% error rate), escalates to Layer 2 Agent, issues redirection
- `before_task_create` now enforces redirection by blocking dead-end task types
- `after_plan` warns if Commander ignores active redirection
- `after_execute` sets redirection on consecutive failures, clears on successful tasks

### Worker agent_loop fixes (root cause of "8 iterations exhausted")
- **Reduced max iterations**: 8 → 5
- **Forced output at iteration 4**: removes tools from the call, demands final JSON
- **Prompt updated**: "Limit yourself to at most 3 tool calls per task. After collecting results, output your JSON."
- Result: all tasks now complete reliably (was ~60% failure rate due to loop exhaustion)

### JSON Schema generation fix for union types
- `dict | None` was resolving to `"string"` because `__origin__` attribute access fails on `types.UnionType`
- **Fix**: use `typing.get_origin()` and `typing.get_args()` instead of direct `__origin__`/`__args__` access
- `_resolve_type()` now handles `X | None`, `Optional[X]`, `Union[X, None]`
- `http_get` headers param now correctly shows as `"type": "object"` in LLM tool schema
- **Hard-won rule**: NEVER use direct `__origin__` access on type annotations — use `typing.get_origin()`

### Tool description improvements
- `http_get`, `http_post`: added `:param:` docstrings with examples → schema now shows `"X-Auth-Token": "abc123"` as example
- Description updated: "Set custom headers (e.g. X-Auth-Token) via the headers dict"

### Commander prompt hardening
- Added `headers={"X-Auth-Token": "token_value"}` format examples in tool catalog
- Added rule: "When registration yields an API token: include exact token value in instruction with explicit headers format"
- Template instruction example prevents Commander from saying "use the token" without specifying HOW

### End-to-end test: Supervisor target flag captured
- `challenge/stage2_supervisor/test_supervisor.py` (port 8889) — designed to trigger Supervisor behaviors
- Attack chain: directory scan → /config (token auth) → /debug (API paths) → /register (get token) → /api/flag with X-Auth-Token header → **FLAG: CTF{supervisor_validated_2024}**
- 9 rounds, 25 findings, flag captured
- Supervisor redirection system validated: Commander pivoted when warned, compaction triggered correctly

### targets/ → challenge/ reorganization
- Moved `targets/` → `challenge/` with staged subdirectories
- `challenge/stage1_basic/` — original CTF Corp Portal (14 endpoints, port 8888)
- `challenge/stage2_supervisor/` — Supervisor validation traps + dead ends (port 8889)
- Updated all references in CLAUDE.md, README.md, docs/architecture.md
- Created `challenge/README.md` with stage catalog and run instructions

