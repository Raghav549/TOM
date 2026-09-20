# TOM

**TOM (Task-Oriented Multimodal)** is an open-source-first personal AI agent runtime designed to understand requests, plan multi-step work, use tools, remember context, operate browsers/devices through explicit adapters, and require approval for high-impact actions.

## Design principles
- Open-source-first model/provider adapters; no model lock-in.
- Local-first memory and configuration where practical.
- Explicit tool permissions and approval gates.
- Provider-neutral APIs and replaceable infrastructure.
- No fake capabilities: adapters report unavailable capabilities instead of pretending.
- Core, Android, browser, voice and frontend communicate through correlated task/event streams.
- Action success is effect-verified, not inferred from an ACK or generic screen change.

## Runtime layers
`tom/runtime.py` orchestrates planning → policy → tool execution → verification → memory.
`tom/planner.py` and `tom/providers.py` provide the rule planner and the OpenAI-compatible model adapter.
`tom/memory.py` provides durable local memory with a replaceable storage boundary.
`tom/tools.py` and `tom/permissions.py` contain safe tool contracts and permission enforcement.
`tom/browser` provides the Playwright browser safety/session boundary.
`tom/api/bridge_server.py` provides authenticated Android WSS, action correlation and post-action verification.
`tom/api/voice_ws.py` is the full-duplex voice transport (16 kHz PCM in, streamed 24 kHz PCM out).
`tom/perception` provides screenshot/UI-tree fusion and multimodal verification.
`tom/voice` provides streaming ASR, neural VAD, turn prediction, prosody tracking, barge-in and streaming TTS contracts.
`tom/security` contains redaction, environment-text guards and privacy boundaries.
`tom/public_api_tools.py` provides real read-only public API adapters.
`tom/integration_registry.py` reports configured external providers without pretending unavailable integrations exist.
`tom/production.py` provides a truthful production-readiness report.
`android/` is the Kotlin device agent; `frontend/` is the live-activity web view.

## Quick start
1. Install Python 3.11+.
2. `pip install -e '.[dev]'`
3. Copy `.env.example` to `.env`.
4. Optionally start an OpenAI-compatible model server or configure another provider.
5. `uvicorn tom.api.app:app --reload`
6. Inspect `/health`, `/ready`, `/v1/capabilities`, and `/v1/integrations`.
7. Send a request: `POST /v1/agent {"message": "..."}`; approve pending steps with `POST /v1/agent/approve`.

See `Quickstart.md` for a walkthrough and `docs/PRODUCTION.md` for the release checklist.

## HTTP / WebSocket surface
| Endpoint | Purpose |
| --- | --- |
| `GET /health`, `GET /ready` | liveness and truthful readiness report |
| `POST /v1/agent`, `POST /v1/agent/approve`, `GET /v1/agent/{id}/pending`, `GET /v1/tasks/{id}` | agent runtime |
| `GET/POST /v1/profile` | companion identity and preferences |
| `GET /v1/capabilities`, `GET /v1/integrations`, `GET /v1/public-apis` | capability discovery |
| `GET /v1/credentials/status`, `POST/DELETE /v1/credentials` | encrypted credential vault |
| `GET /v1/integrations/google/*` | Google OAuth browser flow |
| `WS /v1/events/ws` | correlated live event stream for the frontend |
| `WS /v1/voice/ws` | full-duplex voice loop |
| `WS /v1/device/live`, `WS /ws` | authenticated Android bridge |
| `POST /v1/voice/synthesize`, `/v1/tts/qwen3/*` | TTS |

## Safety model
Every tool declares a risk class. Read-only tools can run automatically when permitted. External side effects such as sending messages, purchases, account changes, deletion, or device control require an approval token unless the user explicitly configured a lower-risk policy.

The Android bridge uses challenge/HMAC authentication, sequence checks and task/action correlation. Post-action state must be observed before TOM treats an action as verified.

## Research basis
The verifier/recovery architecture is informed by V-Droid, VeriSafe Agent, VeriGUI, AndroidWorld, OSWorld, Qwen UI-Agent and Qwen-CUA. See `docs/VERIFIER_RESEARCH_2026.md` for the engineering mapping.

## License
Apache-2.0. See `LICENSE`.
