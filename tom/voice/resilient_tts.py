from __future__ import annotations

import os
from collections.abc import Iterator

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


class ResilientTTS:
    """Primary/secondary TTS routing with truthful failure semantics."""

    def __init__(self) -> None:
        from .indic_parler_stream import IndicParlerStreamingAdapter
        from .qwen_space_stream import Qwen3TTSSpaceAdapter

        self.primary = Qwen3TTSSpaceAdapter()
        self.fallback = IndicParlerStreamingAdapter()
        self.last_backend = ""

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        prompt = text.strip()
        if not prompt:
            return
        primary_error: Exception | None = None
        if os.getenv("TOM_QWEN3_TTS_SPACE_ENABLED", "true").lower() not in {"0", "false", "no"}:
            try:
                chunks = list(self.primary.stream(prompt, language=language, voice=voice, style=style))
                if chunks:
                    self.last_backend = "qwen3-tts-space"
                    yield from chunks
                    return
                primary_error = RuntimeError("Qwen3-TTS Space returned zero audio chunks")
            except Exception as exc:  # noqa: BLE001 - provider boundary
                primary_error = exc
        try:
            chunks = list(self.fallback.stream(prompt, language=language, voice=voice, style=style))
            if not chunks:
                raise RuntimeError("Indic Parler-TTS returned zero audio chunks")
            self.last_backend = "indic-parler"
            yield from chunks
        except Exception as fallback_error:  # noqa: BLE001 - provider boundary
            details = f"primary={primary_error!s}; fallback={fallback_error!s}"
            raise RuntimeError(f"TOM TTS exhausted all configured backends: {details}") from fallback_error


def build_resilient_tts() -> ResilientTTS:
    return ResilientTTS()
