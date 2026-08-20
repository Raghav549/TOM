from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("/kaggle/working/TOM")
MODEL_DIR = Path("/kaggle/working/models/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
PORT = 8787
CLOUDFLARED = Path("/kaggle/working/cloudflared")
TUNNEL_LOG = Path("/kaggle/working/tom-qwen3-cloudflared.log")
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def wait_http(url: str, timeout: float = 180.0) -> None:
    deadline = time.time() + timeout
    last_error = "unknown"
    while time.time() < deadline:
        try:
            with urlopen(Request(url, method="GET"), timeout=5) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except Exception as exc:  # noqa: BLE001 - retry readiness probe
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(2)
    raise RuntimeError(f"TOM Qwen3 health did not become ready: {last_error}")


def ensure_cloudflared() -> None:
    if CLOUDFLARED.exists():
        CLOUDFLARED.chmod(0o755)
        return
    import urllib.request

    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    print("Downloading cloudflared...")
    urllib.request.urlretrieve(url, CLOUDFLARED)
    CLOUDFLARED.chmod(0o755)


def main() -> None:
    if not ROOT.is_dir():
        raise SystemExit(f"TOM checkout not found at {ROOT}; clone the repository there first.")
    if not MODEL_DIR.is_dir():
        raise SystemExit(
            f"Qwen3 model not found at {MODEL_DIR}. Run the ModelScope download cell first."
        )

    token = os.getenv("TOM_QWEN3_TTS_AUTH_TOKEN", "").strip() or secrets.token_urlsafe(32)
    env = os.environ.copy()
    env.update(
        {
            "TOM_ENV": "production",
            "TOM_HOST": "0.0.0.0",
            "TOM_PORT": str(PORT),
            "TOM_TTS_ENGINE": "qwen3",
            "TOM_QWEN3_TTS_MODEL": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
            "TOM_QWEN3_TTS_MODEL_DIR": str(MODEL_DIR),
            "TOM_QWEN3_TTS_DEVICE": "cuda:0",
            "TOM_QWEN3_TTS_DTYPE": "bfloat16",
            "TOM_QWEN3_TTS_STREAMING": "true",
            "TOM_QWEN3_TTS_AUTH_TOKEN": token,
        }
    )

    print("Starting TOM Qwen3 production worker...")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tom.api.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
        ],
        cwd=ROOT,
        env=env,
    )
    try:
        wait_http(f"http://127.0.0.1:{PORT}/v1/tts/qwen3/health")
        print("LOCAL QWEN3 HEALTH: READY")

        ensure_cloudflared()
        empty_config = Path("/tmp/tom-empty-cloudflared.yml")
        empty_config.write_text("", encoding="utf-8")
        print("Starting free TryCloudflare tunnel...")
        with TUNNEL_LOG.open("w", encoding="utf-8") as log:
            tunnel = subprocess.Popen(
                [
                    str(CLOUDFLARED),
                    "--config",
                    str(empty_config),
                    "tunnel",
                    "--no-autoupdate",
                    "--protocol",
                    "http2",
                    "--url",
                    f"http://127.0.0.1:{PORT}",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

        public_url = None
        deadline = time.time() + 60
        while time.time() < deadline:
            text = TUNNEL_LOG.read_text(encoding="utf-8", errors="replace") if TUNNEL_LOG.exists() else ""
            match = TUNNEL_URL_RE.search(text)
            if match:
                public_url = match.group(0)
                break
            if tunnel.poll() is not None:
                raise RuntimeError("cloudflared exited before publishing a public URL")
            time.sleep(1)

        if not public_url:
            raise RuntimeError(f"cloudflared did not publish a URL. See {TUNNEL_LOG}")

        public_health = f"{public_url}/v1/tts/qwen3/health"
        wait_http(public_health, timeout=60)
        stream_url = f"{public_url}/v1/tts/qwen3/stream/{token}"

        print("\n================ TOM QWEN3 PUBLIC API ================")
        print("HEALTH:", public_health)
        print("STREAM:", stream_url)
        print("TOKEN:", token)
        print("\nSet these on the TOM control-plane runtime:")
        print(f"export TOM_QWEN3_TTS_STREAM_URL='{stream_url}'")
        print(f"export TOM_QWEN3_TTS_AUTH_TOKEN='{token}'")
        print("========================================================\n")
        print("Keep this notebook session and cloudflared process alive.")
        print("This free URL is temporary and changes after the session/tunnel stops.")

        tunnel.wait()
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    main()
