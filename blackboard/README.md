# Blackboard — State Plane

## Role

The single source of truth for the entire system. All agents read from and write to the blackboard. No agent communicates directly with another agent.

**Does one thing: store and serve state. Findings are append-only — never modified after write.**

## Files

| File | Role |
|---|---|
| `schema.py` | All system data types: Goal, Task, Finding, EventLog, Decision, WorkerFinding, TaskResult |
| `blackboard.py` | CRUD + JSON persistence + compaction + commander view |

## Data Models

### Goal
- `id`, `description`, `status` (pending/running/completed/failed), `created_at`

### Task
- `id`, `goal_id`, `type`, `status` (pending/assigned/running/completed/failed)
- `assigned_to`, `instruction`, `input_data`, `output_data`
- `created_at`, `completed_at`

### Finding (append-only)
- `id`, `source_task_id`, `type` (vulnerability/credential/flag/asset/info)
- `title`, `data` (dict), `confidence` (0.0-1.0), `timestamp`

### Situation Summary (compaction output)
- LLM-generated structured summary stored separately from findings
- Fields: `summary`, `flags`, `vulnerabilities`, `assets`, `credentials`, `key_observations`, `recommended_steps`
- Updated by `compact()`, read by Commander via `get_commander_view()`

### EventLog
- `timestamp`, `agent_name`, `action`, `detail`

### Decision (Commander → Engine contract)
- `decision` ("continue" | "completed" | "failed"), `reasoning`, `new_tasks`, `final_summary`
- `from_llm_output(dict)` — validates LLM output, raises ValueError on invalid decision value
- `Decision.failed(reason)` — convenience factory for error states

### WorkerFinding (Worker → Engine contract, pre-enrichment)
- `type` (asset/vulnerability/flag/credential/info), `title`, `data`, `confidence`, `source_task_id`
- Engine enriches into `Finding` (adds id + timestamp) before writing to blackboard

### TaskResult (Worker → Engine contract)
- `status` ("completed" | "failed"), `summary`, `output_data`, `findings: list[WorkerFinding]`, `error_detail`
- `to_dict()` / `from_dict(d)` — serialization for JSON persistence
- ALL Worker.execute() calls MUST return this type

## API Surface

### Core CRUD
| Method | Caller | Purpose |
|---|---|---|
| `create_goal(description)` | Engine | Initialize mission |
| `get_goal()` | Commander | Read current objective |
| `update_goal_status(status)` | Commander | Mark complete/failed |
| `create_task(type, instruction, input_data)` | Commander | Publish new subtask |
| `get_pending_tasks()` | Engine | Find unassigned tasks |
| `assign_task(task_id, worker_name)` | Engine | Route task to worker |
| `complete_task(task_id, output_data)` | Worker | Submit results |
| `add_finding(finding)` | Worker | Record discovery (append-only) |
| `get_findings()` | — | Read all intelligence |
| `get_findings_by_type(type)` | — | Filter by type |
| `add_event(agent, action, detail)` | All | Append audit log |
| `get_recent_events(n)` | Commander | Read recent history |
| `snapshot()` | Worker, Hooks | Full state dump (for Workers who need detail) |

### Compaction (added 2026-05-24)
| Method | Caller | Purpose |
|---|---|---|
| `_needs_compact(threshold=3000)` | Engine | Check if findings data exceeds threshold |
| `compact(client, model)` | Engine | LLM summarization → situation_summary |
| `get_commander_view()` | Engine→Commander | Compressed view: summary + recent findings + stats |

## Persistence

MVP uses a single JSON file at `data/blackboard.json`. Every mutation triggers an atomic write (write to temp file → rename). Cleared between runs (new goal = fresh blackboard).
