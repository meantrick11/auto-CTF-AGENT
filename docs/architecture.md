# CTFAgent Architecture (v2)

## Design Principles

1. **One module, one thing**: Each module has one clear responsibility. No module does two jobs.
2. **Brain-Body Decoupling**: Commander decides. Worker executes. They never import each other.
3. **State-Driven**: All coordination through Blackboard. No direct agent-to-agent communication.
4. **Hook Extension**: New capabilities (Context Manager, Evaluator, Monitor) plug in via hooks. Zero engine changes.

## Subsystem Overview

| Module | One Thing | LLM? | Status |
|---|---|---|---|
| **Blackboard** | 信息交换 + 短期记忆 (单次运行) | No | Implemented |
| **Commander** | 读状态, 定攻击方向, 分配 Worker | Yes (1/round) | Implemented |
| **Worker** | 接收方向, 执行任务, 返回 Findings | Yes (tool loop) | Implemented |
| **Engine** | 驱动循环, 按方向并行调度 | No | Implemented |
| **Context Manager** | 信息质量控制: Filter(规则) + Compact(LLM) | Phase 2 only | Filter done, Compact done, merge pending |
| **Evaluator** | 策略评估: 偏移检测, 死胡同标记, 提醒 Commander | Optional | New |
| **Monitor** | 横切度量: token, 耗时, 成功率 | No | New |
| **Memory** | 跨运行持久知识 (RAG) | — | Deferred |

## Data Flow (v2)

```
User Goal
    │
    ▼
┌──────────┐  Direction[]  ┌──────────────────┐
│ Commander │──────────────→│     Engine       │
│ (decide)  │←──────────────│  (drive + route) │
└──────────┘  View+Notes   └──────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              Worker#1      Worker#2      Worker#N
              (sqli dir)    (xss dir)     (...)
                    │             │             │
                    └─────────────┼─────────────┘
                                  ▼
                    ┌──────────────────────┐
                    │   Context Manager    │
                    │  Filter → Compact    │
                    └──────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────┐
                    │     Blackboard       │
                    └──────────────────────┘
                         │            │
                         ▼            ▼
                   ┌──────────┐  ┌──────────┐
                   │Evaluator │  │ Monitor  │
                   │方向纠偏   │  │量化记录   │
                   └──────────┘  └──────────┘
                         │
                         ▼
                  提醒写入 Blackboard
                  Commander 下轮读到
```

## Directory Map

```
CTFAgent/
├── main.py                  # CLI entry
├── config.py                # API client factory, SSL
├── utils.py                 # extract_json, retry_llm_call
├── hooks.py                 # Hook event system
│
├── blackboard/              # 信息交换 + 短期记忆
│   ├── schema.py            # ALL system data types
│   └── blackboard.py        # CRUD + JSON persistence
│
├── commander/               # 战术决策
│   ├── agent.py
│   └── prompts/
│
├── workers/                 # 执行层
│   ├── base_worker.py       # BaseWorker ABC
│   ├── registry.py          # WorkerRegistry
│   └── web/agent.py         # WebWorker
│
├── orchestrator/            # 主循环
│   └── engine.py
│
├── tools/                   # 工具库
│   ├── registry.py          # ToolRegistry + JSON Schema
│   ├── shared/              # encoding, network
│   └── web/                 # recon, exploit
│
├── supervisor/              # 免疫系统 — safety + quality + drift + maintenance
│   ├── safety.py            # Layer 1: 安全规则
│   ├── quality.py           # Layer 1: Finding 去重/规范化
│   ├── drift.py             # Layer 1: 漂移/重复/死胡同检测
│   ├── maintenance.py       # Layer 1: compaction 触发 + observer notes
│   ├── agent.py             # Layer 2: LLM 语义审查
│   └── prompts/
│
├── filter/                  # [已弃用] → supervisor/quality.py
├── guardrail/               # [已弃用] → supervisor/safety.py
│
├── memory/                  # [将来] 跨运行持久知识
│
└── challenge/               # 本地靶场（按阶段）
```

## MVP vs v2 vs Deferred

| Feature | Status |
|---|---|
| Commander + WebWorker + Blackboard | ✅ MVP |
| Filter (dedup + normalize) | ✅ MVP |
| Decision dataclass + schema enforcement | ✅ v2 done |
| TaskResult/WorkerFinding in schema.py | ✅ v2 done |
| Finding.status (suspected/confirmed/dead_end) | ⬜ v2 todo |
| Context Manager (merge Filter + Compact) | ⬜ v2 todo |
| Evaluator (drift detection) | ⬜ v2 todo |
| Monitor (metrics tracking) | ⬜ v2 todo |
| Multi-Worker parallel (direction-based) | ⬜ v2 todo |
| Memory / RAG | 🔵 Deferred |
| Guardrail | 🔵 Deferred |
| Multi-domain workers (Crypto, RE) | 🔵 Deferred |
