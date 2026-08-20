from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


class HybridExpressiveTTS:
    """Language-aware open voice stack with graceful model fallback."""

    def __init__(self) -> None:
        self.qwen: Any | None = None

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        raise RuntimeError("Hybrid voice routing is disabled; configure TOM_TTS_ENGINE=qwen3")


def build_streaming_tts():
    engine = os.getenv("TOM_TTS_ENGINE", "qwen3").strip().lower()
    qwen_engines = {"qwen3", "qwen3-tts", "qwen"}
    if os.getenv("TOM_ENV", "development").strip().lower() == "production" and engine not in qwen_engines:
        raise RuntimeError("production TOM voice must use the Qwen3-TTS engine")
    if engine in qwen_engines:
        from .qwen3_tts_stream import Qwen3TTSStreamingAdapter

        return Qwen3TTSStreamingAdapter()
    raise RuntimeError(f"TOM_TTS_ENGINE must be qwen3; got {engine}")
