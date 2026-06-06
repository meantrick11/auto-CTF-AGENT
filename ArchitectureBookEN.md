# Architecture Design Document for LLM-Driven Multi-Agent Penetration Testing System

## 1. Project Vision & Core Philosophy

This project aims to build an AI-driven penetration testing and CTF-solving hub capable of high autonomy, complex logical reasoning, and continuous state tracking. The system abandons the traditional monolithic model where a single large language model directly operates underlying commands, adopting three core design principles:

* **Brain-Body Decoupling:** Physically isolate logical reasoning (the LLM) from action execution (underlying tools), communicating strictly via standard protocols.
* **Multi-Role Collaboration (Swarm):** Implement a swarm architecture that decomposes complex tasks and distributes them to specialized agents equipped with distinct system prompts.
* **State-Driven & Domain-Driven Design (DDD):** Rely on a globally shared blackboard as the single source of truth. This prevents direct agent-to-agent communication storms and ensures task progress is persistent and traceable.

## 2. Global Topology

The system utilizes a **Hierarchical Star Topology**.
The "Shared Blackboard" and "Event Bus" serve as the central data hub. A central command node handles global scheduling and routing, while multiple stateless execution nodes are attached to the periphery. There is no peer-to-peer communication among nodes; all coordination is achieved by reading from and writing to the global state bus.

## 3. Core Subsystem Division

At a macro level, the system is divided into four well-defined subsystems:

1. **Orchestration Plane (The Brain):** The highest decision-making layer. Responsible for receiving original tasks, intent recognition, macro-tactical planning (SOP generation), task decomposition, and distribution.
2. **State Plane (The Memory):** The global memory repository (Shared Blackboard). Responsible for the structured storage of asset inventories, vulnerability clues, verified credentials, and the current state of the task queue.
3. **Action Plane (The Muscle):** The execution layer. Responsible for claiming specific tasks, invoking underlying security components for probing or exploitation, and performing noise reduction, data cleaning, and key information extraction on massive raw logs.
4. **Guardrail Plane (The Shield):** The baseline security valve. Responsible for compliance verification of inbound and outbound instructions, and triggering human-in-the-loop interruptions prior to high-risk operations.

## 4. Agent Swarm Role Definition

To achieve the principle of least privilege and maintain focused attention, the agents within the system are assigned the following core roles:

* **The Commander:** Possesses only the authority to read the blackboard and assign tasks. Responsible for macro-strategy formulation, resource routing, and determining goal completion.
* **Domain Workers:** Independent worker nodes segmented by specific cybersecurity domains (e.g., Web, Cryptography, Reverse Engineering, Binary Exploitation, Forensics). They lack macro-planning capabilities and only execute tactical actions within their specific domain.
* **The Filter (Data Washer):** A middleware agent dedicated to log noise reduction. It converts lengthy, chaotic outputs from the workers into high-entropy, structured summaries to prevent context overload for the Commander.
* **The Guardrail:** A monitoring node independent of the primary business flow. It audits all outbound instructions in real-time and triggers security circuit breakers when necessary.

## 5. Tool Library Architecture

The underlying tool pool (Skill/Action layer) utilizes a dual-layer allocation architecture to reduce communication overhead and ensure specialization:

* **Shared Utilities:** Contains foundational capabilities such as data encoding/decoding, hash calculations, and lightweight network requests. These tools are registered in the base environment of all Domain Workers, allowing them to be invoked locally at any time without requesting permission from the Commander.
* **Domain-Specific Weapons:** Contains specialized capabilities such as heavy scanners, advanced mathematical sandboxes, and decompilers. These tools are strictly isolated via permission controls and exposed only to the corresponding Domain Workers.

## 6. Standard Business Flow Model

The standard operational lifecycle of the system is as follows:

1. **Task Input:** Target information and requirements are injected into the global blackboard.
2. **Tactical Planning:** The Commander reads the blackboard, generates phase-specific tasks, and publishes them to the event bus.
3. **Security Compliance:** The Guardrail subsystem verifies the safety and authorization of the task instructions.
4. **Task Routing & Execution:** The Commander routes the task to the appropriate Domain Worker. The Worker invokes the corresponding tools (shared or domain-specific) to perform the action.
5. **Perception & Noise Reduction:** Raw outputs from the tools are passed to the Filter node, which extracts the core intelligence.
6. **State Convergence:** The cleaned intelligence is written back to the global blackboard, updating the asset or vulnerability tree.
7. **Reflection & Iteration:** Based on the newly updated intelligence on the blackboard, the Commander decides whether the final goal has been met or if a new round of planning is required. This cycle repeats until the objective is achieved or all strategies are exhausted.

## 7. Implementation Status (MVP, 2026-05-23)

### Implemented (aligned with blueprint)
- **Orchestration Plane**: Commander agent reads snapshot, outputs JSON decision. No tools.
- **State Plane**: Blackboard with Goal/Task/Finding/EventLog. JSON persistence, atomic writes.
- **Action Plane**: 1 WebWorker (LLM + OpenAI tool-calling loop). Returns TaskResult.
- **Tool Library**: 15 tools across shared (encoding, network) and web (recon, exploit) categories. Singleton ToolRegistry with @register_tool decorator.
- **Hook System**: 7 event points embedded in engine. Filter/Guardrail plug in via hooks with zero engine changes.

### Added (beyond original blueprint — architectural safeguards)
- **WorkerRegistry**: Singleton, prefix-based routing. Replaces hardcoded worker dict. Adding a new Worker = one `reg.register()` call — no routing code changes.
- **TaskResult + WorkerFinding**: Dataclass contract enforced at BaseWorker level. Filter, Engine, and Blackboard all depend on this schema. Prevents "every Worker returns different dict shape" chaos.
- **Worker contract**: `execute()` MUST return `TaskResult`. Engine normalizes both TaskResult and plain dicts for backward compat with hook modifications.

### Deferred (match blueprint §6 steps 3 & 5)
- **Filter (Data Washer)**: Implemented — hooks into `after_execute`, dedup + normalize + truncate-mark. Rule-based, no LLM.
- **Guardrail (Safety Shield)**: 3 hook points ready (`before_plan`, `before_task_create`, `before_execute`). No implementation yet.
- **Multi-domain Workers**: Web only. Crypto/RE/PWN/Forensics not started.
- **Concurrency**: Serial loop only. Blueprint's "stateless execution nodes" imply parallel execution — not yet.
- **Persistent memory / RAG**: Not in original blueprint. Identified as gap.