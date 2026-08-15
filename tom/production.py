from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True
