# TOM Qwen3 TTS — Kaggle GPU deployment

Kaggle is the authoritative free GPU runtime for the tested TOM Qwen3-TTS backend.

The production API served by this deployment is the real TOM endpoint:

`POST /v1/tts/qwen3/stream`

`GET /v1/tts/qwen3/health`

## Kaggle setup

1. Create a Kaggle Code notebook.
2. Enable Internet and select a GPU accelerator (the tested setup used NVIDIA Tesla T4).
3. Clone the TOM repository into `/kaggle/working/TOM`.
4. Install the repository's `voice-qwen` dependencies.
5. Download `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` into `/kaggle/working/models/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` using ModelScope.
6. Set `TOM_QWEN3_TTS_DEVICE=cuda:0` and the model directory above.
7. Start `uvicorn tom.api.app:app --host 0.0.0.0 --port 8787`.

## Verified path

The tested Kaggle path has already completed real model loading, real `generate_custom_voice()` inference, TOM adapter conversion to PCM16, and a real HTTP request returning `200` with audio bytes. No mock/fallback audio is part of this path.

## Important runtime limitation

Kaggle notebook GPU sessions are temporary. The API is live only while the notebook session is running. A public URL requires a tunnel or another externally reachable proxy; the URL may change when the session restarts. This is free testing/live infrastructure, not guaranteed 24/7 hosting.

Do not switch the production TTS factory to a hosted demo, Hugging Face ZeroGPU, Android system TTS, tone generation, or another silent fallback. If the Kaggle GPU is unavailable, TOM must report TTS unavailable rather than fabricate success.
