# CTFAgent — Daily Progress

## 2026-05-23 — MVP Complete

- Core loop: Commander → Blackboard → Worker → loop, end-to-end verified
- 15 registered tools (encoding, network, web recon/exploit)
- test_target.py: local vulnerable HTTP server
- DeepSeek API via OpenAI SDK
- Base64 decode scenario: 2 rounds, flag captured
- HTTP attack scenario: 2 rounds, 10 findings, flag captured
- TaskResult + WorkerFinding enforced schema
- WorkerRegistry prefix-based routing
- Hook system with 7 event points

## 2026-05-24 — Stability + Context Compression

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
- `test_target.py`: 14 endpoints, multi-step CTF (not one-shot flag)
- Flag only in `/admin` (requires login chain)
- Tested end-to-end: 7 rounds, 14 findings, flag captured

### Documentation
- Module responsibility principle: "each module does ONE thing well"
- READMEs updated: filter/, blackboard/, orchestrator/, commander/
- CLAUDE.md synced with current state
