# TOM

**TOM (Task-Oriented Multimodal)** is an open-source-first personal AI agent runtime designed to understand requests, plan multi-step work, use tools, remember context, operate browsers/devices through explicit adapters, and require approval for high-impact actions.

## Design principles
- Open-source-first model/provider adapters; no model lock-in.
- Local-first memory and configuration where practical.
- Explicit tool permissions and approval gates.
- Provider-neutral APIs and replaceable infrastructure.
- No fake capabilities: adapters report unavailable capabilities instead of pretending.
- Core, Android, browser, voice and frontend communicate through correlated task/event streams.

## Runtime layers
`tom/core` orchestrates perception → planning → tool execution → verification.
`tom/models` provides model/provider adapters.
`tom/memory.py` provides durable local memory with a replaceable storage boundary.
`tom/tools` contains safe tool contracts and permission enforcement.
`tom/browser` provides the Playwright browser safety/session boundary.
`tom/api/bridge_server.py` provides authenticated Android WSS, action correlation and post-action verification.
`tom/perception` provides screenshot/UI-tree fusion and multimodal verification.
`tom/voice` provides streaming ASR, neural VAD, turn prediction, prosody tracking, barge-in and streaming TTS contracts.
`tom/public_api_tools.py` provides real read-only public API adapters.
`tom/integration_registry.py` reports configured external providers without pretending unavailable integrations exist.
`tom/production.py` provides a truthful production-readiness report.

## Quick start
1. Install Python 3.11+.
2. `pip install -e '.[dev]'`
3. Copy `.env.example` to `.env`.
4. Start an OpenAI-compatible model server or configure another provider.
5. `uvicorn tom.api.app:app --reload`
6. Inspect `/health`, `/ready`, `/v1/capabilities`, and `/v1/integrations`.

For the production path and release checklist see `docs/PRODUCTION.md`.

## Safety model
Every tool declares a risk class. Read-only tools can run automatically when permitted. External side effects such as sending messages, purchases, account changes, deletion, or device control require an approval token unless the user explicitly configured a lower-risk policy.

The Android bridge uses challenge/HMAC authentication, sequence checks and task/action correlation. Post-action state must be observed before TOM treats an action as verified.

## License
Apache-2.0. See `LICENSE`.
