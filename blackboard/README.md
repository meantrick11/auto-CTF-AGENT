# Blackboard — State Plane

## Role

The single source of truth for the entire system. All agents read from and write to the blackboard. No agent communicates directly with another agent.

## Files

| File | Role | Input | Output |
|---|---|---|---|
| `schema.py` | Data model definitions (Goal, Task, Finding, EventLog) | — | Dataclass/typed dict definitions |
| `blackboard.py` | CRUD operations + JSON file persistence | Method calls from Commander/Worker/Engine | Updated state, persisted to `data/blackboard.json` |

## Data Models

### Goal
- `id`, `description`, `status` (pending/running/completed/failed), `created_at`

### Task
- `id`, `goal_id`, `type` (web_recon/web_exploit), `status` (pending/assigned/running/completed/failed)
- `assigned_to`, `instruction` (NL for Worker), `input_data`, `output_data`
- `created_at`, `completed_at`

### Finding
- `id`, `source_task_id`, `type` (vulnerability/credential/flag/asset/info)
- `title`, `data` (dict), `confidence` (0.0-1.0), `timestamp`

### EventLog
- `timestamp`, `agent_name`, `action`, `detail`

## API Surface

| Method | Caller | Purpose |
|---|---|---|
| `create_goal(description)` | Engine | Initialize mission |
| `get_goal()` | Commander | Read current objective |
| `update_goal_status(status)` | Commander | Mark complete/failed |
| `create_task(type, instruction, input_data)` | Commander | Publish new subtask |
| `get_pending_tasks()` | Engine | Find unassigned tasks |
| `assign_task(task_id, worker_name)` | Engine | Route task to worker |
| `get_assigned_task(worker_name)` | Worker | Get my work item |
| `complete_task(task_id, output_data)` | Worker | Submit results |
| `add_finding(finding)` | Worker | Record discovery |
| `get_findings()` | Commander | Read all intelligence |
| `get_findings_by_type(type)` | Commander | Filter by type |
| `add_event(agent, action, detail)` | All | Append audit log |
| `get_recent_events(n)` | Commander | Read recent history |
| `snapshot()` | All | Full state dump |

## Persistence

MVP uses a single JSON file at `data/blackboard.json`. Every mutation triggers an atomic write (write to temp file → rename).
