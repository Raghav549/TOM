from __future__ import annotations

import os
import asyncio
import importlib.util
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    configured: bool
    detail: str


class ProductionReadiness:
    """Truthful production-readiness report; never turns missing adapters into green checks."""

    def __init__(self) -> None:
        self.environment = os.getenv("TOM_ENV", "development")

    def checks(self) -> list[CapabilityCheck]:
        model = bool(os.getenv("TOM_LLM_ENABLED", "false").lower() == "true" and os.getenv("TOM_LLM_MODEL", "").strip())
        tts = bool(os.getenv("TOM_TTS_ENGINE", "").strip())
        asr = bool(os.getenv("TOM_ASR_MODEL", "").strip())
        vad = os.getenv("TOM_NEURAL_VAD", "true").lower() not in {"0", "false", "no"}
        turn = bool(os.getenv("TOM_TURN_MODEL_PATH", "").strip())
        vision = bool(os.getenv("TOM_VISION_BASE_URL", "").strip() and os.getenv("TOM_VISION_MODEL", "").strip())
        browser = _module_available("playwright")
        device_secret = bool(os.getenv("TOM_DEVICE_SECRETS_JSON", "").strip())
        data_dir = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
        return [
            CapabilityCheck("model", model, "LLM provider configured" if model else "configure TOM_LLM_ENABLED/TOM_LLM_MODEL"),
            CapabilityCheck("tts", tts, "TTS engine selected" if tts else "configure TOM_TTS_ENGINE"),
            CapabilityCheck("asr", asr, "ASR model selected" if asr else "configure TOM_ASR_MODEL"),
            CapabilityCheck("neural_vad", vad, "neural VAD enabled" if vad else "neural VAD disabled"),
            CapabilityCheck("learned_turn", turn, "ONNX turn model configured" if turn else "TOM_TURN_MODEL_PATH not configured"),
            CapabilityCheck("vision", vision, "vision provider configured" if vision else "configure TOM_VISION_BASE_URL/TOM_VISION_MODEL"),
            CapabilityCheck("browser", browser, "Playwright installed" if browser else "install the browser extra"),
            CapabilityCheck("device_auth", device_secret, "device secret store configured" if device_secret else "configure secure device secrets"),
            CapabilityCheck("persistent_data", True, f"data directory: {data_dir}"),
        ]

    def report(self) -> dict[str, object]:
        checks = self.checks()
        return {
            "environment": self.environment,
            "ready": all(item.configured for item in checks),
            "checks": [item.__dict__ for item in checks],
            "policy": "A capability is executable only when its adapter is configured and its permission gate allows it.",
        }

    async def probe(self, *, browser: Any = None, device_sessions: Any = None) -> dict[str, object]:
        checks = {item.name: item for item in self.checks()}
        await self._probe_llm(checks)
        await self._probe_tts(checks)
        await self._probe_local_models(checks)
        await self._probe_browser(checks, browser)
        self._probe_persistence(checks)
        if self.environment.lower() == "production":
            connected = bool(device_sessions)
            checks["device_auth"] = CapabilityCheck(
                "device_auth", connected,
                "authenticated Android device connected" if connected else "no authenticated Android device connected",
            )
        return {
            "environment": self.environment,
            "ready": all(item.configured for item in checks.values()),
            "checks": [item.__dict__ for item in checks.values()],
            "policy": "Readiness requires configured and reachable dependencies; unavailable capabilities fail closed.",
        }

    async def _probe_llm(self, checks: dict[str, CapabilityCheck]) -> None:
        if not checks["model"].configured:
            return
        base_url = os.getenv("TOM_LLM_BASE_URL", "").rstrip("/")
        headers = {"Authorization": f"Bearer {os.getenv('TOM_LLM_API_KEY', '').strip()}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/models", headers=headers)
                response.raise_for_status()
            checks["model"] = CapabilityCheck("model", True, "Qwen OpenAI-compatible endpoint is reachable")
        except Exception as exc:  # noqa: BLE001 - readiness reports provider failures
            checks["model"] = CapabilityCheck("model", False, f"Qwen LLM endpoint unavailable: {type(exc).__name__}")

    async def _probe_tts(self, checks: dict[str, CapabilityCheck]) -> None:
        if os.getenv("TOM_TTS_ENGINE", "qwen3").strip().lower() not in {"qwen3", "qwen3-tts", "qwen"}:
            checks["tts"] = CapabilityCheck("tts", False, "production TTS engine must be Qwen3-TTS")
            return
        url = os.getenv("TOM_QWEN3_TTS_STREAM_URL", "").strip()
        if not url:
            checks["tts"] = CapabilityCheck("tts", False, "configure TOM_QWEN3_TTS_STREAM_URL for the Qwen3-TTS service")
            return
        health_url = url.removesuffix("/stream") + "/health"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)
                response.raise_for_status()
            checks["tts"] = CapabilityCheck("tts", True, "Qwen3-TTS streaming service is reachable and model-loaded")
        except Exception as exc:  # noqa: BLE001
            checks["tts"] = CapabilityCheck("tts", False, f"Qwen3-TTS service unavailable: {type(exc).__name__}")

    async def _probe_local_models(self, checks: dict[str, CapabilityCheck]) -> None:
        if checks["asr"].configured:
            try:
                from tom.voice.streaming_asr import StreamingFasterWhisper
                await asyncio.to_thread(StreamingFasterWhisper()._load)
                checks["asr"] = CapabilityCheck("asr", True, "faster-whisper model loaded")
            except Exception as exc:  # noqa: BLE001
                checks["asr"] = CapabilityCheck("asr", False, f"ASR model unavailable: {type(exc).__name__}")
        if checks["neural_vad"].configured:
            try:
                from tom.voice.neural_vad import SileroStreamingVAD
                await asyncio.to_thread(SileroStreamingVAD()._load)
                checks["neural_vad"] = CapabilityCheck("neural_vad", True, "Silero VAD model loaded")
            except Exception as exc:  # noqa: BLE001
                checks["neural_vad"] = CapabilityCheck("neural_vad", False, f"VAD model unavailable: {type(exc).__name__}")
        if checks["learned_turn"].configured:
            path = Path(os.getenv("TOM_TURN_MODEL_PATH", ""))
            checks["learned_turn"] = CapabilityCheck("learned_turn", path.is_file(), "turn model file exists" if path.is_file() else "turn model file does not exist")

    async def _probe_browser(self, checks: dict[str, CapabilityCheck], browser: Any) -> None:
        if not checks["browser"].configured or browser is None:
            return
        try:
            await browser.start()
            await browser.close()
            checks["browser"] = CapabilityCheck("browser", True, "Playwright browser launched and closed")
        except Exception as exc:  # noqa: BLE001
            checks["browser"] = CapabilityCheck("browser", False, f"Playwright launch failed: {type(exc).__name__}")

    def _probe_persistence(self, checks: dict[str, CapabilityCheck]) -> None:
        data_dir = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".readiness-", delete=True):
                pass
            checks["persistent_data"] = CapabilityCheck("persistent_data", True, f"data directory is writable: {data_dir}")
        except OSError as exc:
            checks["persistent_data"] = CapabilityCheck("persistent_data", False, f"data directory is not writable: {type(exc).__name__}")


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True
