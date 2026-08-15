# TOM

**TOM (Task-Oriented Multimodal)** is an open-source-first personal AI agent runtime designed to understand requests, plan multi-step work, use tools, remember context, operate browsers/devices through explicit adapters, and require approval for high-impact actions.

## Design principles
- Open-source-first model/provider adapters; no model lock-in.
- Local-first memory and configuration where practical.
- Explicit tool permissions and approval gates.
- Provider-neutral APIs and replaceable infrastructure.
- No fake capabilities: adapters report unavailable capabilities instead of pretending.
- Frontend is intentionally separate from the core runtime.

## Core modules
`tom/core` orchestrates perception → planning → tool execution → verification.
`tom/models` provides model/provider adapters.
`tom/memory` provides durable semantic/episodic memory interfaces.
`tom/tools` contains safe tool contracts and permission enforcement.
`tom/integrations` contains browser, APIs, notifications and device adapters.
`tom/api` exposes the runtime through FastAPI.

## Quick start
1. Install Python 3.11+.
2. `pip install -e '.[dev]'`
3. Copy `.env.example` to `.env`.
4. Start an OpenAI-compatible local model server (for example Ollama) or configure another provider.
5. `uvicorn tom.api.app:app --reload`

The web UI is deliberately not included in this phase. Build and harden the runtime first, then connect a frontend/client.

## Safety model
Every tool declares a risk class. Read-only tools can run automatically when permitted. External side effects such as sending messages, purchases, account changes, deletion, or device control require an approval token unless the user explicitly configured a lower-risk policy.

## License
Apache-2.0. See `LICENSE`.
