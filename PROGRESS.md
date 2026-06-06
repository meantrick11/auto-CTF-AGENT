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

### To do next (v2 implementation order)
1. Finding.status field (suspected/confirmed/dead_end) — schema change
2. Merge Filter + Compactor into `context/` module
3. Commander: add "hold" decision + direction allocation (not task-level)
4. Evaluator module: rule-based drift detection, write observer_notes
5. Monitor module: metrics tracking
6. Multi-Worker parallel execution (direction-based grouping)
