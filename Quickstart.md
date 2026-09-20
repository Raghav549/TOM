# TOM Quickstart

Get a local TOM control plane running in about five minutes. No model, GPU or
Android device is required for the first run: TOM starts in a truthful degraded
mode and reports exactly which capabilities are missing.

## 1. Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

## 2. Run the server

```bash
uvicorn tom.api.app:app --reload --port 8787
```

Check it is alive:

```bash
curl -s localhost:8787/health
curl -s localhost:8787/ready | python -m json.tool
curl -s localhost:8787/v1/capabilities | python -m json.tool
```

`/ready` lists every capability (`model`, `tts`, `asr`, `browser`, `device_auth`,
…) with `configured: true|false`. Nothing is simulated: an unconfigured
capability is reported as unavailable instead of pretending to work.

## 3. Talk to the agent

```bash
curl -s localhost:8787/v1/agent \
  -H 'content-type: application/json' \
  -d '{"message": "search for the weather in Delhi", "conversation_id": "demo-1"}' | python -m json.tool
```

Read-only tools run immediately. Side-effecting steps (send, pay, delete …) come
back in `pending_approval`; approve one explicitly:

```bash
curl -s localhost:8787/v1/agent/approve \
  -H 'content-type: application/json' \
  -d '{"conversation_id": "demo-1", "tool_index": 0}'
```

Watch the live event stream for that task in the browser: open
`frontend/index.html`, enter `demo-1` as the task id and connect (add
`?api=ws://localhost:8787` to the page URL if the frontend is served elsewhere).

## 4. Add a real LLM (optional)

TOM speaks the OpenAI-compatible chat protocol, so any local or hosted server works:

```dotenv
TOM_LLM_ENABLED=true
TOM_LLM_BASE_URL=http://127.0.0.1:11434/v1   # Ollama, vLLM, llama.cpp, ModelScope …
TOM_LLM_MODEL=qwen3:8b
TOM_LLM_API_KEY=                              # required by hosted providers
```

Without an LLM the deterministic rule planner and friendly fallback responder are
used, which is enough to exercise the approval and event pipeline.

## 5. Voice, Android and browser

* **Voice** — `/v1/voice/ws` streams 16 kHz PCM16 in and 24 kHz PCM16 out. It
  needs `faster-whisper` (`pip install -e '.[voice]'`) and a Qwen3-TTS endpoint
  (`TOM_QWEN3_TTS_STREAM_URL`, see `deploy/kaggle-qwen3/`).
* **Android** — build the app in `android/` (see `android/README.md`), provision a
  device secret in `TOM_DEVICE_SECRETS_JSON`, and point the app at your `wss://`
  endpoint. Live connectivity shows up under `/ready` → `operational`.
* **Browser** — `pip install -e '.[browser]' && playwright install chromium`
  enables the Playwright tools.

## 6. Run the checks

```bash
ruff check .
pytest -q
python scripts/validate_production.py   # advisory outside TOM_ENV=production
```

For the full production checklist see `docs/PRODUCTION.md`.
