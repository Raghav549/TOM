# TOM Qwen3 TTS — Kaggle GPU deployment

Kaggle is the authoritative free GPU runtime for the tested TOM Qwen3-TTS backend.

The worker serves the **same real TOM FastAPI endpoint** used by the production adapter:

- `GET /v1/tts/qwen3/health`
- `POST /v1/tts/qwen3/stream/<TOKEN>`

The model is loaded locally from ModelScope files. The public tunnel is only transport; it does not provide the TTS model.

## Why this is the chosen free path

The repository's real Qwen3-TTS checkpoint has already been downloaded and tested on a Kaggle NVIDIA T4. Real `Qwen3TTSModel.generate_custom_voice()` inference succeeded, TOM converted the waveform to PCM16, and the real HTTP endpoint returned `200` with audio bytes. No mock audio or alternate hosted TTS is involved.

The official Qwen3-TTS 0.6B CustomVoice model supports 10 languages, including English. TOM currently exposes English through this production route; it does not silently pretend that Hindi/Hinglish/Bengali are supported.

## Kaggle setup

1. Open the TOM Kaggle notebook in the Kaggle UI.
2. In **Settings → Session options**, enable **Internet**.
3. Select a GPU accelerator. The verified run used **NVIDIA Tesla T4**.
4. Clone TOM into `/kaggle/working/TOM` if it is not already there.
5. Install the pinned Qwen dependencies from the repository (`pip install -e '.[voice-qwen]'`).
6. Download the exact checkpoint:

```bash
modelscope download \
  --model Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
  --local_dir /kaggle/working/models/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
  --max-workers 2
```

7. Run the public worker from a Python cell:

```python
%run /kaggle/working/TOM/deploy/kaggle-qwen3/start.py
```

The script will:

- verify the local model directory;
- start TOM's real FastAPI Qwen3 service on port `8787`;
- wait for `/v1/tts/qwen3/health` to become `READY`;
- download `cloudflared` if necessary;
- create a free TryCloudflare HTTP/2 tunnel;
- verify the public health endpoint;
- generate a random 32-byte-equivalent bearer token;
- print the exact public `STREAM` URL and the environment variables to copy to the TOM control plane.

## Configure TOM

Copy the two printed values into the runtime that needs remote TTS:

```bash
export TOM_TTS_ENGINE=qwen3
export TOM_QWEN3_TTS_STREAM_URL='https://YOUR-TUNNEL.trycloudflare.com/v1/tts/qwen3/stream/YOUR_TOKEN'
export TOM_QWEN3_TTS_AUTH_TOKEN='YOUR_TOKEN'
```

The adapter validates the TOM PCM protocol before accepting any audio. The server returns framed mono PCM16 at 24 kHz and terminates with an explicit end frame.

## Verify from the TOM control plane

After setting the environment variables, run the normal production readiness probe. TTS is green only if the remote health endpoint is reachable and reports `READY`. A failed Kaggle session remains red/unavailable; TOM does not fabricate speech.

## Important runtime limitation

Kaggle notebook GPU sessions are temporary. The free TryCloudflare URL is also temporary and changes when the tunnel/session restarts. Kaggle currently documents finite notebook session execution and TryCloudflare documents its quick tunnels as testing/development infrastructure, not guaranteed production hosting.

So the **code path is production-grade and fail-closed**, but free Kaggle + TryCloudflare is not a guaranteed 24/7 production host. For permanent production uptime, move this same worker to a persistent GPU runtime or a managed GPU service without changing TOM's TTS protocol.

Do not switch the production TTS factory to a hosted demo, Hugging Face ZeroGPU, Android system TTS, tone generation, or another silent fallback.
