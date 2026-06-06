# CTFAgent

LLM-driven multi-agent autonomous penetration testing system. Built on Brain-Body decoupling, Swarm collaboration, and State-Driven design principles.

**Status:** MVP — Commander + Web Worker + Blackboard, end-to-end verified.

## Architecture

```
User Goal → Blackboard → Commander(plan) → Blackboard(tasks) → Worker(execute+tools) → Blackboard(findings) → loop
```

Six independent modules, single coupling point at the orchestrator:

| Module | Role | Independence |
|---|---|---|
| `commander/` | Tactical brain: reads state, creates tasks, NEVER executes tools | Zero dependencies on workers/tools/blackboard |
| `workers/web/` | Web security specialist: claims tasks, calls tools, extracts findings | Zero dependencies on commander/blackboard |
| `workers/registry.py` | Singleton WorkerRegistry: prefix-based task routing | Depends only on base_worker.py |
| `workers/base_worker.py` | TaskResult + WorkerFinding schema contract + BaseWorker ABC | Zero dependencies on agents |
| `blackboard/` | Single source of truth: Goal/Task/Finding CRUD + JSON persistence | Zero dependencies on anything |
| `tools/` | 15 tools: encoding, HTTP, web recon, web exploit | Zero dependencies on agents |
| `orchestrator/` | Main loop: wires all components, drives Commander-Worker cycles | The ONLY coupling point |
| `config.py` / `utils.py` | API client factory, SSL config, JSON extraction | Shared utilities |

**Commander and Worker never talk to each other.** All coordination through the Blackboard.

## Quick Start

```powershell
# 1. Setup
cp .env.example .env          # Edit .env with your DeepSeek API key
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Simple test — base64 decode (no target needed)
python main.py -g "Decode this base64: ZmxhZ3t0ZXN0X2ZsYWd9" -n 5

# 3. Full attack test — needs local target
# Terminal 1:
python targets/test_target.py
# Terminal 2:
python main.py -g "Attack http://localhost:8888 and capture the flag" -n 8
```

## Requirements

- Python 3.10+
- DeepSeek API key (set in `.env`)
- `openai>=1.0.0`, `python-dotenv>=1.0.0`

## CLI

```
python main.py -g "goal description" [-n max_rounds] [-m model] [-o report.json]
```

| Flag | Default | Description |
|---|---|---|
| `-g` / `--goal` | (required) | Mission goal in natural language |
| `-n` / `--max-rounds` | 10 | Max Commander-Worker cycles |
| `-m` / `--model` | deepseek-chat | LLM model |
| `-o` / `--output` | (none) | Save final report as JSON |
| `-d` / `--data-dir` | data | Blackboard persistence directory |

## What It Can Do

- Web directory scanning, form extraction, HTTP header analysis
- SQL injection, XSS, command injection probing
- Base64/hex/URL encoding and decoding
- Autonomous multi-round attack planning and execution
- Structured finding extraction (asset, vulnerability, credential, flag)
- Full audit trail via event log

## What's Deferred (not in MVP)

- Guardrail agent (safety checks) — 3 hook points ready, not yet implemented
- Cross-task memory / RAG knowledge base
- Multi-domain workers (Crypto, RE, PWN, Forensics)
- MCP external tool integration
- Database persistence (JSON file only)
- Concurrent worker execution

## Project Structure

```
CTFAgent/
├── main.py                  # CLI entry point
├── config.py                # API client, SSL, .env loading
├── utils.py                 # extract_json() helper
│
├── targets/                  # Local vulnerable test range
│   ├── README.md             # Target catalog & attack chains
│   └── test_target.py        # CTF Corp Portal (14 endpoints)
├── requirements.txt
├── .env.example
│
├── blackboard/              # State Plane — shared memory
│   ├── schema.py            # Goal, Task, Finding, EventLog
│   └── blackboard.py        # CRUD + JSON persistence
│
├── commander/               # Orchestration Plane — tactical brain
│   ├── agent.py             # Reads snapshot, outputs JSON decisions
│   └── prompts/
│
├── workers/                 # Action Plane — execution muscle
│   ├── registry.py          # WorkerRegistry (singleton, prefix routing)
│   ├── base_worker.py       # TaskResult + WorkerFinding + BaseWorker ABC
│   └── web/                 # Web security specialist
│       ├── agent.py         # LLM + tool-calling loop
│       └── prompts/
│
├── tools/                   # Tool library
│   ├── registry.py          # @register_tool decorator + JSON Schema gen
│   ├── shared/              # encoding, network (all workers)
│   └── web/                 # recon, exploit (web worker only)
│
├── orchestrator/            # Main engine — the coupling point
│   └── engine.py            # Commander-Worker-Blackboard loop
│
└── docs/
    └── architecture.md      # Architecture overview
```

## Contributing

Adding a new domain worker:
1. Create `workers/<domain>/agent.py` extending `BaseWorker`, implement `execute() → TaskResult`
2. Write domain-specific system prompt
3. Register tools under `tools/<domain>/` using `@register_tool`
4. In `engine.__init__`: add `reg.register(Worker(model), name=..., domain=..., task_prefixes=[...])`
5. Commander needs zero changes (task routing is prefix-based)

## License

MIT
