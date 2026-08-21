from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    configured: bool
    detail: str
    required: bool = False


class ProductionReadiness:
    """Truthful production-readiness report with infrastructure and capability separation.

    ``ready`` answers whether the deployed server is healthy enough to serve traffic.
    Optional TOM capabilities remain visible as degraded/unavailable without making the
    whole web process unready. Live Android connectivity is operational state only.

    Required checks are configurable through TOM_REQUIRED_CAPABILITIES, for example:
    ``device_auth,persistent_data,model``. The safe default is infrastructure only.
    """

    DEFAULT_REQUIRED = frozenset({"device_auth", "persistent_data"})

    def __init__(self) -> None:
        self.environment = os.getenv("TOM_ENV", "development")

    def _required_names(self) -> set[str]:
        raw = os.getenv("TOM_REQUIRED_CAPABILITIES", "").strip()
        if not raw:
            return set(self.DEFAULT_REQUIRED)
        return {item.strip() for item in raw.split(",") if item.strip()}

    def checks(self) -> list[CapabilityCheck]:
        required = self._required_names()
        llm_enabled = os.getenv("TOM_LLM_ENABLED", "true").lower() == "true"
        llm = bool(
            not llm_enabled
            or (
                os.getenv("TOM_LLM_BASE_URL", "https://api-inference.modelscope.cn/v1").strip()
                and os.getenv("TOM_LLM_MODEL", "Qwen/Qwen3-8B").strip()
                and os.getenv("TOM_LLM_API_KEY", "").strip()
            )
        )
        tts_engine = os.getenv("TOM_TTS_ENGINE", "qwen3").strip().lower()
        tts_enabled = tts_engine in {"qwen3", "qwen3-tts", "qwen"}
        tts = bool(
            not tts_enabled
            or os.getenv("TOM_QWEN3_TTS_STREAM_URL", "").strip()
            or os.getenv("TOM_QWEN3_TTS_MODEL_DIR", "").strip()
        )
        asr = bool(os.getenv("TOM_ASR_MODEL", "").strip())
        vad = os.getenv("TOM_NEURAL_VAD", "true").lower() not in {"0", "false", "no"}
        turn = bool(os.getenv("TOM_TURN_MODEL_PATH", "").strip())
        vision = bool(os.getenv("TOM_VISION_BASE_URL", "").strip() and os.getenv("TOM_VISION_MODEL", "").strip())
        browser = _module_available("playwright")
        device_secret = bool(os.getenv("TOM_DEVICE_SECRETS_JSON", "").strip())
        data_dir = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))

        items = [
            CapabilityCheck("model", llm, "LLM disabled" if not llm_enabled else ("LLM endpoint configured" if llm else "configure TOM_LLM_BASE_URL/TOM_LLM_API_KEY/TOM_LLM_MODEL"), "model" in required),
            CapabilityCheck("tts", tts, "TTS disabled" if not tts_enabled else ("Qwen3-TTS endpoint or local model configured" if tts else "configure TOM_QWEN3_TTS_STREAM_URL or local model directory"), "tts" in required),
            CapabilityCheck("asr", asr, "ASR model selected" if asr else "ASR not configured", "asr" in required),
            CapabilityCheck("neural_vad", vad, "neural VAD enabled" if vad else "neural VAD disabled", "neural_vad" in required),
            CapabilityCheck("learned_turn", turn, "ONNX turn model configured" if turn else "TOM_TURN_MODEL_PATH not configured", "learned_turn" in required),
            CapabilityCheck("vision", vision, "vision provider configured" if vision else "vision provider not configured", "vision" in required),
            CapabilityCheck("browser", browser, "Playwright installed" if browser else "browser capability unavailable", "browser" in required),
            CapabilityCheck("device_auth", device_secret, "device secret store configured" if device_secret else "configure secure device secrets", "device_auth" in required),
            CapabilityCheck("persistent_data", True, f"data directory: {data_dir}", "persistent_data" in required),
        ]
        return items

    async def probe(self, *, browser: Any = None, device_sessions: Any = None) -> dict[str, object]:
        checks = {item.name: item for item in self.checks()}
        await self._probe_llm(checks)
        await self._probe_tts(checks)
        await self._probe_local_models(checks)
        await self._probe_browser(checks, browser)
        self._probe_persistence(checks)

        connected = bool(device_sessions)
        checks["device_connected"] = CapabilityCheck(
            "device_connected",
            connected,
            "authenticated Android device connected" if connected else "no authenticated Android device currently connected",
            False,
        )

        required_checks = [item for item in checks.values() if item.required]
        failed_required = [item.name for item in required_checks if not item.configured]
        degraded = [item.name for item in checks.values() if not item.required and item.name != "device_connected" and not item.configured]
        ready = not failed_required
        return {
            "environment": self.environment,
            "ready": ready,
            "required_capabilities": [item.name for item in required_checks],
            "failed_required_capabilities": failed_required,
            "degraded_capabilities": degraded,
            "operational": {"device_connected": connected},
            "checks": [item.__dict__ for item in checks.values()],
            "policy": "Readiness is based only on configured required server dependencies. Optional capabilities and live Android connectivity are reported separately and do not block server readiness unless explicitly listed in TOM_REQUIRED_CAPABILITIES.",
        }

    async def _probe_llm(self, checks: dict[str, CapabilityCheck]) -> None:
        if not checks["model"].configured or os.getenv("TOM_LLM_ENABLED", "true").lower() != "true":
            return
        base_url = os.getenv("TOM_LLM_BASE_URL", "https://api-inference.modelscope.cn/v1").rstrip("/")
        key = os.getenv("TOM_LLM_API_KEY", "").strip()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        request_payload = {
            "model": os.getenv("TOM_LLM_MODEL", "Qwen/Qwen3-8B"),
            "messages": [{"role": "user", "content": "Reply exactly TOM_READY"}],
            "stream": True,
            "extra_body": {"enable_thinking": False},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=request_payload) as response:
                    response.raise_for_status()
                    saw_delta = False
                    saw_done = False
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            saw_done = True
                            break
                        try:
                            payload = __import__("json").loads(data)
                        except ValueError:
                            continue
                        choices = payload.get("choices") or []
                        if choices:
                            delta = (choices[0] or {}).get("delta") or {}
                            if isinstance(delta.get("content"), str) and delta.get("content"):
                                saw_delta = True
                    if not saw_delta or not saw_done:
                        raise RuntimeError("Qwen endpoint did not return a complete SSE response")
            checks["model"] = _replace_check(checks["model"], True, "Qwen/ModelScope SSE chat completion verified")
        except Exception as exc:  # noqa: BLE001
            checks["model"] = _replace_check(checks["model"], False, f"Qwen LLM endpoint unavailable: {type(exc).__name__}")

    async def _probe_tts(self, checks: dict[str, CapabilityCheck]) -> None:
        if not checks["tts"].configured:
            return
        url = os.getenv("TOM_QWEN3_TTS_STREAM_URL", "").strip()
        if not url and os.getenv("TOM_TTS_ENGINE", "qwen3").strip().lower() not in {"qwen3", "qwen3-tts", "qwen"}:
            return
        try:
            if url:
                health_url = _qwen3_health_url(url)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(health_url, headers=_tts_headers())
                    response.raise_for_status()
                    payload = response.json()
                if not isinstance(payload, dict) or payload.get("status") != "READY":
                    raise RuntimeError("Qwen3-TTS health endpoint did not report READY")
                checks["tts"] = _replace_check(checks["tts"], True, "Qwen3-TTS streaming service is reachable and model-loaded")
                return
            from tom.voice.qwen3_tts_stream import Qwen3TTSStreamingAdapter
            await asyncio.to_thread(Qwen3TTSStreamingAdapter()._load)
            checks["tts"] = _replace_check(checks["tts"], True, "local Qwen3-TTS checkpoint loaded")
        except Exception as exc:  # noqa: BLE001
            checks["tts"] = _replace_check(checks["tts"], False, f"Qwen3-TTS unavailable: {type(exc).__name__}: {str(exc)[:180]}")

    async def _probe_local_models(self, checks: dict[str, CapabilityCheck]) -> None:
        if checks["asr"].configured:
            try:
                from tom.voice.streaming_asr import StreamingFasterWhisper
                await asyncio.to_thread(StreamingFasterWhisper()._load)
                checks["asr"] = _replace_check(checks["asr"], True, "faster-whisper model loaded")
            except Exception as exc:  # noqa: BLE001
                checks["asr"] = _replace_check(checks["asr"], False, f"ASR model unavailable: {type(exc).__name__}")
        if checks["neural_vad"].configured:
            try:
                from tom.voice.neural_vad import SileroStreamingVAD
                await asyncio.to_thread(SileroStreamingVAD()._load)
                checks["neural_vad"] = _replace_check(checks["neural_vad"], True, "Silero VAD model loaded")
            except Exception as exc:  # noqa: BLE001
                checks["neural_vad"] = _replace_check(checks["neural_vad"], False, f"VAD model unavailable: {type(exc).__name__}")
        if checks["learned_turn"].configured:
            path = Path(os.getenv("TOM_TURN_MODEL_PATH", ""))
            checks["learned_turn"] = _replace_check(checks["learned_turn"], path.is_file(), "turn model file exists" if path.is_file() else "turn model file does not exist")

    async def _probe_browser(self, checks: dict[str, CapabilityCheck], browser: Any) -> None:
        if not checks["browser"].configured or browser is None:
            return
        try:
            await browser.start()
            await browser.close()
            checks["browser"] = _replace_check(checks["browser"], True, "Playwright browser launched and closed")
        except Exception as exc:  # noqa: BLE001
            checks["browser"] = _replace_check(checks["browser"], False, f"Playwright launch failed: {type(exc).__name__}")

    def _probe_persistence(self, checks: dict[str, CapabilityCheck]) -> None:
        data_dir = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".readiness-", delete=True):
                pass
            checks["persistent_data"] = _replace_check(checks["persistent_data"], True, f"data directory is writable: {data_dir}")
        except OSError as exc:
            checks["persistent_data"] = _replace_check(checks["persistent_data"], False, f"data directory is not writable: {type(exc).__name__}")


def _replace_check(item: CapabilityCheck, configured: bool, detail: str) -> CapabilityCheck:
    return CapabilityCheck(item.name, configured, detail, item.required)


def _qwen3_health_url(stream_url: str) -> str:
    """Map either /stream or /stream/<token> to the authoritative /health URL."""
    parsed = urlsplit(stream_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("TOM_QWEN3_TTS_STREAM_URL must be an absolute http(s) URL")
    marker = "/v1/tts/qwen3/stream"
    index = parsed.path.find(marker)
    if index < 0:
        raise ValueError("TOM_QWEN3_TTS_STREAM_URL must contain /v1/tts/qwen3/stream")
    base_path = parsed.path[:index]
    return f"{parsed.scheme}://{parsed.netloc}{base_path}/v1/tts/qwen3/health"


def _tts_headers() -> dict[str, str]:
    token = os.getenv("TOM_QWEN3_TTS_AUTH_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True
