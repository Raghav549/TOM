# TOM audit and repair report — 2026-10-05

## Status: repaired defects, NOT production certification

This change set does **not** fulfill the requested complete, hardware-verified overhaul. It repairs reproducible configuration, planning, runtime, approval, authentication, streaming-contract, memory, and typing defects. Real Qwen3 inference and speech generation remain blocked in this environment. Do not deploy this as a certified unrestricted autonomous agent.

No screenshots were attached. The reported `TASK_STARTED → TASK_FAILED` symptom was traced to concrete code paths, not correlated with a user's screenshot or machine logs.

### Inspection coverage

- Enumerated and read all 294 originally tracked files with a file-by-file byte/line/marker scan, including Python, Android, frontend, deployment, tests, and documentation.
- Manually traced the core configuration → provider → planner → runtime → tool → verification → approval and voice paths. This is not a claim that every line of the Android/frontend/deployment code received an exhaustive manual security review.
- Final source tree has 142 Python files under `tom`; lint/type/import checks are described below.
- Architecture remains split: `AgentRuntime` uses `tom.tools.ToolRegistry`; other action paths use `tom.tool_registry.ToolRegistry`. `LiveDeviceLoop` and live-task bridging replan on observations. Existing deterministic adapters and legacy paths have not been comprehensively consolidated.

## Verified root causes and changes

### Model selection and planning

Files: `tom/config.py`, `tom/providers.py`, `tom/planner.py`, `tom/production.py`, `.env.example`, `.env.production.example`, `tom/api/app.py`.

1. `_llm_enabled()` previously required an API key, silently disabling keyless Ollama. It now honors the enable flag without imposing cloud authentication.
2. Defaults now use `http://127.0.0.1:11434/v1` and the exact Ollama tag `qwen3:4b`. Explicit configured model names are preserved. Settings now read environment values on construction rather than freezing dataclass defaults at import time.
3. API-created `ModelPlanner` fails visibly by default. `TOM_PLANNER_ALLOW_FALLBACK=true` explicitly enables deterministic recovery. Recovery is rejected if it references an unregistered tool; failure is logged and recovery is labeled in the plan explanation.
4. Registry risk is authoritative. A model labeling a high-risk tool `read` no longer silently switches planners; the registered high risk is applied.
5. Completed Qwen reasoning blocks are removed before JSON parsing. Invalid structured output gets one model repair attempt before failure/recovery.
6. The HTTP payload no longer nests SDK-only `extra_body` on the wire. SSE must terminate with `[DONE]`; truncated content is not returned as a successful completion. Network/protocol failures, existing bounded pre-output retries, a total deadline, and an output-size limit are enforced. Partial output is never retried into duplicate text.
7. LLM timeout and task/tool limits are configurable. This is the real HTTP OpenAI-compatible Ollama path, not a native `/api/chat` implementation.

### Runtime, task failure, approval, and receipts

Files: `tom/runtime.py`, `tom/response.py`, `tom/api/app.py`, `tom/device/core_receiver.py`, `tom/api/bridge_server.py`.

1. An empty plan previously created an execution task, then failed it because no tool result existed. Empty plans now return a conversational response without fabricated execution success/failure events.
2. `ApprovalGate.approve()` returns a string; dereferencing `token.token` crashed approval execution. The returned string is now passed correctly.
3. Approval updates step/task state, prevents same-conversation concurrent approval/handle execution, requires dependency order, and stops queued dependent actions after failure. Pending approvals cannot be overwritten by a new `handle()` request.
4. Execution stops at the first approval boundary instead of executing later steps before their prerequisite is approved.
5. Previously a retry decision was recorded but the loop advanced to the next step. Read-risk actions now retry up to the existing three-attempt limit; failed prerequisites stop execution. Side effects are not blindly replayed.
6. Tool execution gets an async deadline. Failure dictionaries with `success=false` or an error are not treated as success. Terminal events include errors, and exceptions log task/action/tool/step identifiers with traceback.
7. `LiveExecutionContext.action_finished(success, error)` was called with `(action_id, bool)`, making failed actions look successful. Call signatures are corrected.
8. Friendly fallback now recognizes the actual `action.failed` / `action.finished` event names.
9. Plans exceeding 40 steps are rejected rather than silently truncated.
10. Android `CoreBridgeReceiver` was constructed with the result callback in the two-argument plan-callback slot. It now uses `on_result=` explicitly. Distinct verification/result types no longer share incorrectly typed variables.

### Authentication and API boundaries

Files: `tom/api/app.py`, `tom/api/auth.py`, `tom/api/voice_ws.py`, `tom/api/device_ws.py`.

- HTTP `/v1/` operator endpoints enforce `TOM_API_TOKEN` whenever configured and fail closed without it in production. Qwen TTS uses its separate token. OAuth callback remains protected by its existing OAuth state validation rather than requiring a browser bearer header.
- Event, voice, and standalone multimodal WebSockets now check operator bearer authorization before acceptance. Paired-device live protocols retain their separate authentication.
- API requests cannot inject private runtime context fields such as `_precomputed_plan` or `approved`.
- Planning/provider errors return an actionable 503 rather than an uncaught server traceback; plan validation errors return 422.
- This remains a single-operator token model, **not** multi-tenant identity/authorization. Browser WebSocket clients need an authenticated same-origin proxy capable of adding the header; direct browser clients cannot set arbitrary Authorization headers. UI support for this deployment flow is not completed here.

### Local documents and memory

Files: `tom/local_tools.py`, `tom/memory.py`, `tom/semantic_conversation_memory.py`.

- Opt-in `TOM_WORKSPACE_DIR` registers real `filesystem.list` and `filesystem.read` tools. Reads return byte counts and SHA-256 receipts. UTF-8 reads are capped at 256 KiB; listings at 500 entries. Absolute paths, traversal, hidden paths, and symlinks are rejected.
- This is read-only confinement, not an OS sandbox. Do not expose a workspace containing secrets or writable by an adversary who can race path checks. It intentionally does not add arbitrary terminal execution, writes, deletion, persistence, or privilege escalation.
- JSONL reading no longer loads the whole file into one string; candidate retention is bounded. Corrupt JSON records generate a warning rather than destroying valid history.
- Semantic merge previously filtered out all recent records by comparing against the wrong identity set; corrected.
- The two semantic-memory adapters now request cached embedding models only, preventing implicit downloads in offline operation.

### Qwen3-TTS and PCM16

Files: `pyproject.toml`, `tom/voice/qwen3_tts_service.py`, `tom/voice/qwen3_tts_stream.py`.

- Confirmed via `pip index versions qwen-tts` that release 0.1.1 is available. Replaced the streaming-fork Git dependency with `qwen-tts==0.1.1`, matching the `generate_custom_voice` API actually used.
- Official adapter currently generates a complete waveform and then packetizes it. Health/header diagnostics explicitly report **buffered-inference**. True incremental model generation was not implemented or verified.
- Model loading is locked; local generation is serialized, and the HTTP service rejects concurrent generation with 429. The generation slot remains held in the worker after an HTTP disconnect until native work exits.
- Loads require local checkpoint files; selected-device dtype and CUDA availability/memory checks are corrected. Invalid dtype is rejected instead of silently replaced.
- PCM16 is explicitly little-endian, finite-checked, clipped, and even-byte validated. Malformed terminal frames are rejected.
- Remote TTS no longer has an infinite read timeout. Standard Authorization bearer headers now work; configured tokens are enforced in development too. Unknown voices are rejected rather than silently replaced.
- TTS health loading runs off the event loop. Self-HTTP TTS is no longer the development example default.

### Additional import/type/readiness repairs

Files: `tom/verification.py`, `tom/success_predicates.py`, `tom/tool_registry.py`, `tom/bridge/live_router.py`, `tom/memory_store.py`, `tom/perception/{state_tracker,vision_pipeline,action_plan,openai_compatible_vision}.py`, `tom/persistence.py`, `tom/task_persistence.py`, `tom/voice/{engine,turn_predictor,neural_vad,indic_parler_stream}.py`.

- Removed a nonexistent `tom.perception.ScreenObservation` import; observation conversion accepts the objects it actually handles.
- Corrected optional values, fixed-size coordinate tuples, `list` type shadowing, optional dependency annotations, absent action IDs, and node bounds checks.
- External-command TTS serialized nonexistent `VoiceStyle.value`; it now serializes the actual model and uses explicit UTF-8 subprocess decoding.
- Indic TTS CPU dtype now uses float32 instead of forced float16.
- Readiness distinguishes energy VAD fallback from a loaded neural model, fails unknown required capabilities, and probes a separate real browser instance rather than closing the active user browser.
- CI and dev dependencies now include mypy/build. Added `scripts/smoke_local_models.py`, a real-model probe that returns nonzero on missing models; it never substitutes fixtures.

## Actual execution ledger

Environment: Linux, Python 3.11, approximately 3.8 GiB RAM, no swap; no `ollama`, `nvidia-smi`, `pwsh`, Docker, Gradle, or Java command detected. No local Qwen checkpoints, Torch/Qwen TTS, Playwright browser, or Android device were provisioned.

| Check actually executed | Actual result |
|---|---|
| Initial system `pip install -e '.[dev]'` | Failed: OS externally-managed Python; switched to an isolated venv, did not override OS protection |
| Editable install in `.venv` | Passed |
| Baseline `pytest -q` | 254 passed |
| First provider regression run | 253 passed / 1 failed: old test asserted SDK `extra_body` wire nesting; changed assertion to require the correct flattened field and forbid nesting |
| Core runtime, approval, TTS repair runs | Repeated full runs: 254 passed |
| First added regression suite | 270 passed; repeated after type-driven repairs |
| Initial mypy check | 49 errors across 21 files, including genuine import/signature defects |
| Intermediate mypy check | 22 errors across 13 files |
| Final `mypy tom --ignore-missing-imports` | Passed across 142 Python files; this is not strict checking of absent third-party implementations |
| Readiness regression run | 273 passed / 1 failed: unknown-capability validation was placed after substituted check providers; moved validation to capability construction and reran without weakening the test |
| Final `pytest -q` | **276 passed**, one upstream Starlette/httpx deprecation warning |
| Fresh venv, built wheel + dev dependencies | Installation and `pip check` passed; final repeat recorded below |
| `ruff check .` | Passed |
| `python -m compileall -q tom scripts` | Passed |
| `python -m build` | Wheel and source distribution built successfully |
| Import validation of original source modules | No import failures |
| Installed-wheel module import validation | Passed; final repeat recorded below |
| `git diff --check` | Passed |
| Development config validation with model/TTS/VAD disabled | Advisory command exited 0; `ready=false` because required device auth is absent. Not a readiness certification |
| Actual Uvicorn `/health`, source and clean-wheel server | HTTP 200, version 0.5.3 |
| Actual unauthenticated `/v1/agent` with token configured | HTTP 401 |
| Actual authenticated `/v1/agent`, local-model enabled | HTTP 503 `AGENT_UNAVAILABLE`: connection attempts to Ollama failed |
| Model selection check | `qwen3:4b`, `ModelPlanner`, no API key required |
| Actual direct inference attempt | Failed: no Ollama listener |
| Actual TTS `/health` | HTTP 503 `DEPENDENCY_ERROR`, installation guidance returned |
| Actual TTS `/stream` generation request | HTTP 503, missing Qwen3-TTS dependencies; no audio generated |
| Actual `/ready` from clean-wheel server | HTTP 200 diagnostic body with `ready=false`, missing device auth/model/TTS/browser/vision/ASR/turn/neural-VAD accurately shown |
| `scripts/smoke_local_models.py` | Exit 1: all four certification stages failed/blocked (inference, model-planned file task, HTTP agent, actual TTS) |
| Real filesystem/runtime tests | Passed: actual temporary UTF-8 file read, hash receipt, dry-run approval followed by real read, task completion |
| Recovery/concurrency tests | Passed with explicitly labeled injected failures; not represented as real model failure/recovery |
| Provider/PCM tests | Passed protocol/unit tests; these do not establish model inference or perceptual audio quality |
| Windows, Android APK, Docker builds, real GUI/browser/ASR | Not executed: required platforms/dependencies unavailable |

Tests added cover settings refresh/keyless activation, authoritative risk, Qwen reasoning parsing, explicit fallback, JSON repair, empty plans, real file receipts and approval, read retries, dependency failure stops, concurrency/cancellation slot release, traversal/symlinks/file limits, PCM byte order/clipping, corrupt memory, HTTP auth/private-context rejection, operator WebSocket auth, TTS token enforcement, truncated SSE, failed live state, and unknown required capabilities. Existing tests were not skipped or weakened.

## Setup and reproduction

### Local LLM

Install Ollama on the target machine, start its service, and run:

```text
ollama pull qwen3:4b
ollama list
```

Set the model name to the exact installed tag. Minimum config:

```dotenv
TOM_LLM_ENABLED=true
TOM_LLM_BASE_URL=http://127.0.0.1:11434/v1
TOM_LLM_MODEL=qwen3:4b
TOM_LLM_API_KEY=
TOM_PLANNER_ALLOW_FALLBACK=false
TOM_API_TOKEN=<generate-a-strong-random-value>
```

The token notation above is a documentation instruction, not a usable credential. Generate locally, for example with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Do not commit `.env`.

Install `python -m pip install -e '.[dev]'` in a venv. On Windows use `.venv\Scripts\python.exe` and `.venv\Scripts\pip.exe`; on Linux use `.venv/bin/python` and `.venv/bin/pip`. Start `python -m uvicorn tom.api.app:app --host 127.0.0.1 --port 8787`. Use 0.0.0.0 only behind appropriate authentication/network controls. Container localhost does not reach host Ollama; configure the host/gateway URL explicitly.

Run `python scripts/smoke_local_models.py` with matching `TOM_API_TOKEN`. It must exit 0 on the target host before claiming basic local-model capability.

### Local speech

On a suitably provisioned model host:

```text
python -m pip install -e '.[voice-qwen-local]'
hf download Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice --local-dir .models/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
```

Download models while online; subsequent adapter loads are local-only. Set `TOM_QWEN3_TTS_MODEL_DIR`, `TOM_QWEN3_TTS_DEVICE=auto` (or an actual CPU/CUDA device), and leave `TOM_QWEN3_TTS_STREAM_URL` empty for local generation. Remote service clients need the real service URL and matching token. Existing default memory guards are 8 GiB available CPU RAM / 4 GiB free CUDA VRAM, not guarantees that every model/runtime fits. Do not lower guards merely to make this sandbox pass. Follow upstream platform-specific Torch, driver, and SoX installation requirements. Windows GPU and dependency compatibility are not certified here.

Optional browser: install `.[browser]`, then `python -m playwright install chromium`. Optional ASR: `.[voice]` and a cached Whisper model. Configure required capabilities deliberately; device auth remains required in the example production profile.

## Remaining limitations and work required

1. **Real model certification is blocked.** No actual Qwen3:4b completion, model-selected successful task, or Qwen3 audio waveform was produced. A suitably provisioned host must run the real smoke script and broader task tests.
2. **No exhaustive production/security certification.** Android, GUI, browser selectors and dangerous-action classification, SSRF/egress boundaries, frontend auth integration, voice/WebSocket concurrency, device consent, and cross-user isolation need deployment-specific review and execution.
3. **No general autonomous research/desktop agent transformation.** The fixed runtime plan is not a general observe/replan loop after every non-device action. Tools still have incomplete argument schemas. No arbitrary PowerShell/terminal executor, application launcher, process inspector, document OCR/PDF pipeline, or OS sandbox was added.
4. **No automatic hardware model switching/context tuning.** Explicit model tags are preserved. TTS performs existing best-effort memory/device checks; Windows RAM checks need an available platform-aware backend such as psutil. Ollama residency/concurrency/context/quantization sizing remains operator-managed.
5. **TTS is buffered inference.** Native generation cannot safely be force-cancelled in a Python thread. For hard cancellation/resource isolation use a dedicated worker process/service. HTTP packetization and timeout checks are not low-latency incremental synthesis.
6. **State remains process-local in important paths.** Pending approvals, active-task guards, task maps, and model concurrency guards do not coordinate multiple Uvicorn workers. Use one worker until durable transactional ownership is implemented. Completed task maps are not fully TTL-managed. Cancellation releases admission but does not comprehensively persist terminal state across every live path.
7. **Memory is not uniformly encrypted.** JSONL conversation records remain plaintext and synchronous disk access still occurs in parts of the async runtime. History scan cost remains proportional to the file size despite bounded retained candidates. Secure the data directory and implement rotation/indexed storage before long-running/high-volume use.
8. **Legacy/fallback paths remain.** `RulePlanner` and `FriendlyFallback` remain for backward compatibility and explicit disabled-model/recovery modes. Some deterministic rules reference unavailable tools; enabled ModelPlanner recovery rejects these, but manually selected RulePlanner remains limited. Tests and documentation contain intentional example URLs; a comprehensive endpoint/capability cleanup was not completed.
9. **Health endpoints are diagnostics, not full readiness gates.** `/ready` preserves its HTTP-200 diagnostic contract; deployers must inspect `ready` or use the production validation command. Production API-token availability is enforced at request time and is not yet part of the unified capability gate. Some optional probes can be expensive.
10. **Error/log hardening remains incomplete.** New planner/action diagnostics are useful, but repository-wide secret redaction, bounded logging, and a uniform typed error envelope across all routes were not completed.
11. **Platform builds remain unverified.** No actual Windows subprocess lifecycle test, browser installation/execution, Android build/device run, or Docker build was possible here. The external TTS command path still uses an operator-configured shell command and is not a general sandbox.
12. One upstream test-client deprecation warning remains; no test was silenced to conceal it.

The real-model failures above are deliberately visible. Passing unit tests, type checks, and builds must not be mistaken for satisfying the user's full acceptance criteria.

### Final clean-environment repeat

After the operator-WebSocket changes, rebuilt the final wheel and sdist, reinstalled the wheel into the separate clean venv, and reran the complete checkout test suite: **276 passed, 1 upstream deprecation warning, 9.76 seconds**. `pip check` reported no broken requirements. All **142 installed-wheel modules** imported successfully from outside the checkout. Final lint, mypy, compileall, and whitespace validation passed. Temporary audit HTTP servers were stopped; no test server or model process was left running.
