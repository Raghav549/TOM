from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, bool]
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "checks": self.checks,
            "details": self.details,
        }


def build_readiness(*, llm_enabled: bool, vision_enabled: bool, voice_enabled: bool,
                    android_bridge_enabled: bool, tts_engine: bool, asr_engine: bool,
                    smart_turn: bool) -> ReadinessReport:
    checks = {
        "agent_runtime": True,
        "llm": llm_enabled,
        "vision": vision_enabled,
        "android_bridge": android_bridge_enabled,
        "streaming_tts": voice_enabled and tts_engine,
        "streaming_asr": voice_enabled and asr_engine,
        "smart_turn": voice_enabled and smart_turn,
    }
    # Core HTTP readiness does not require optional capabilities. This is a
    # diagnostic endpoint, not a claim that every advertised capability works.
    return ReadinessReport(
        ready=checks["agent_runtime"],
        checks=checks,
        details={
            "optional_capabilities_missing": [name for name, ok in checks.items() if not ok and name != "agent_runtime"],
        },
    )
