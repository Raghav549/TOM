# TOM production path

The production path is deliberately layered. A green code check does not mean an external provider is configured.

## 1. Browser
- Playwright is the browser adapter.
- Navigation is policy checked before `goto`.
- Page state is captured after actions for grounding and verification.
- Purchases, account changes, downloads with side effects, and other high-impact actions remain approval-gated.

## 2. Android reliability
- The Android bridge uses a challenge/HMAC handshake.
- Every incoming frame carries device identity and a monotonically increasing sequence.
- Actions have unique `action_id` values and are correlated with task IDs.
- Post-action verification requests a fresh UI observation and screenshot.
- A failed/unknown verification must not be treated as success.

## 3. Model and voice deployment
TOM exposes replaceable adapters for an OpenAI-compatible planner, streaming ASR, neural VAD, Smart Turn/learned turn prediction, and streaming TTS. Model files are not committed to the repository. They must be downloaded/licensed and configured through environment variables.

Supported voice languages in the runtime contract: Hindi, English, Hinglish, Bengali. Expressive prosody is driven by the voice director and the configured TTS adapter; TOM does not claim a voice engine is available until it is actually configured.

## 4. Memory
The current durable baseline is local JSONL memory. It is intentionally replaceable. A production deployment should put the data directory on persistent encrypted storage and add retention/export/delete controls before storing sensitive user data.

## 5. Integrations
`/v1/integrations` reports which real providers are configured. Weather, geocoding, and currency have public read-only adapters. Calendar, email, messaging, payments, flights, finance, transport, maps, places, and news remain unavailable until a concrete provider adapter is configured.

## 6. Security
- Keep `.env` out of Git.
- Use HTTPS/WSS at the edge.
- Use >=32-byte device secrets.
- Keep raw credentials out of event payloads and logs.
- Keep approval required for high-impact side effects.
- Do not expose an enrollment endpoint that returns device secrets.

## 7. Observability
The live event stream is the single source for Core, Android bridge, verification, replanning, and frontend activity. Use the event sequence number for replay/debugging and the task ID for correlation.

## 8. E2E validation
A production release should prove, on real configured infrastructure:
1. Android connects and authenticates over WSS.
2. Observation and screenshot arrive with the same task/action correlation.
3. A safe action executes and produces a verified state change.
4. A failed action causes re-grounding/re-planning rather than a fabricated success.
5. Voice supports partial ASR, barge-in, TTS cancellation, and resume where the engine supports it.
6. High-impact actions stop at the approval boundary.

## 9. Deployment
Build the included container, terminate TLS at the deployment edge, persist `TOM_DATA_DIR`, configure model/provider secrets through the platform secret store, and require `/health` and `/ready` checks.

## 10. Final validation
`/ready` is intentionally strict: it is green only when every currently required production check is configured. Missing capabilities are reported as unavailable rather than simulated.
