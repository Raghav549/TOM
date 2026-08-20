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
TOM exposes replaceable adapters for an OpenAI-compatible planner, streaming ASR, neural VAD, Smart Turn/learned turn prediction, and streaming TTS. Model files are not committed to the repository.

### LLM
The default documented provider is ModelScope API-Inference using its OpenAI-compatible endpoint. TOM probes `/models` and fails readiness if the configured provider is unreachable. A real ModelScope access token and a currently supported model ID are still required.

### Qwen3-TTS
The authoritative tested TTS runtime is **Kaggle GPU + ModelScope-local Qwen3-TTS-12Hz-0.6B-CustomVoice**. The Kaggle notebook loads the checkpoint locally and runs the same TOM FastAPI endpoint used by the adapter. No hosted demo, ZeroGPU Space, Android system TTS, tone generator, or silent audio fallback is part of the production factory.

The tested Qwen3 CustomVoice checkpoint supports 10 languages, but TOM's current production router intentionally exposes English only. Hindi, Hinglish, and Bengali are not silently routed to an unvalidated engine; they remain unavailable until a separate real provider is validated.

The free Kaggle deployment is a live GPU runtime, not permanent hosting. Kaggle sessions are temporary, and a free TryCloudflare quick tunnel produces an ephemeral public URL. The code is production-oriented and fail-closed; **24/7 production uptime still requires a persistent GPU host or a managed GPU service**.

For the free path:
1. Enable Kaggle Internet and a GPU.
2. Run `deploy/kaggle-qwen3/start.py` after the model/dependencies are installed.
3. The script starts TOM's real Qwen3 endpoint, creates a free TryCloudflare URL, and prints the tokenized TTS URL.
4. Put that URL into `TOM_QWEN3_TTS_STREAM_URL` on the TOM runtime that needs remote TTS.
5. Keep the printed token private. The tokenized route is the minimum protection for the account-free quick-tunnel deployment.

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
- Keep `TOM_QWEN3_TTS_AUTH_TOKEN` secret when using the public Kaggle TTS route.
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
6. Qwen3-TTS health is `READY` and a real remote TTS request returns framed PCM16 audio.
7. High-impact actions stop at the approval boundary.

## 9. Deployment
Build the included container for the TOM control plane, terminate TLS at the deployment edge, persist `TOM_DATA_DIR`, configure model/provider secrets through the platform secret store, and require `/health` and `/ready` checks. Keep the Kaggle GPU session separate as the free Qwen3-TTS inference worker.

## 10. Final validation
`/ready` is intentionally strict: it is green only when every currently required production check is configured and reachable. Missing capabilities are reported as unavailable rather than simulated.
