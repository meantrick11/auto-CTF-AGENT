# CTFAgent Architecture (MVP)

## Design Principles

1. **Brain-Body Decoupling**: LLM reasoning is physically isolated from tool execution. Communication via standard protocols only.
2. **Multi-Role Swarm**: Complex tasks decomposed and distributed to specialized agents with distinct system prompts.
3. **State-Driven**: A globally shared blackboard serves as the single source of truth. No direct agent-to-agent communication.

## Subsystem Overview

| Plane | Component | Role |
|---|---|---|
| Orchestration | Commander | Read blackboard → plan → publish tasks |
| State | Blackboard | Centralized goal/task/finding storage (JSON file) |
| Action | Web Worker | Claim task → invoke tools → write results |
| Tool Layer | Tools | Shared utilities + domain-specific weapons |

## Data Flow

```
User Input → Blackboard(goal)
  → Commander.plan() → Blackboard(tasks)
  → Worker.execute() → Tools → Blackboard(findings)
  → Commander.plan() → (loop or finish)
```

## MVP Scope

- **In**: Commander, 1 Web Worker, Blackboard (JSON), Tool Registry, Worker Registry, TaskResult schema enforcement, Orchestrator Engine
- **Added beyond original blueprint**: WorkerRegistry (singleton, prefix-based routing), TaskResult + WorkerFinding dataclasses (Action Plane contract enforcement)
- **Out**: Filter (data washer), Guardrail (security sentinel), multi-domain workers, DB persistence, concurrency

## Directory Map

```
CTFAgent/
├── main.py                  # Entry point
├── orchestrator/engine.py   # Main loop
├── commander/agent.py        # Tactical planner
├── workers/
│   ├── registry.py           # WorkerRegistry (singleton, prefix routing)
│   ├── base_worker.py        # TaskResult + WorkerFinding + BaseWorker
│   └── web/agent.py          # Web security executor
├── blackboard/blackboard.py # Shared state CRUD
├── tools/                    # Shared + web tools
└── data/blackboard.json      # Persisted state
```
