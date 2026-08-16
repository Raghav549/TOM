from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


class HybridExpressiveTTS:
    """Language-aware open voice stack with graceful model fallback.

    English and other Qwen-supported languages prefer Qwen3-TTS for fine-grained
    character/style control. Indic languages prefer Indic Parler-TTS. If an optional
    backend is not installed, the adapter falls back to the available open backend.
    """

    def __init__(self) -> None:
        from .indic_parler_stream import IndicParlerStreamingAdapter

        self.indic = IndicParlerStreamingAdapter()
        self.qwen: Any | None = None
        self._qwen_error: str | None = None

    def _qwen_backend(self):
        if self.qwen is not None:
            return self.qwen
        if self._qwen_error:
            return None
        try:
            from .qwen3_tts_stream import Qwen3TTSStreamingAdapter

            self.qwen = Qwen3TTSStreamingAdapter()
            return self.qwen
        except Exception as exc:  # noqa: BLE001 - optional backend boundary
            self._qwen_error = str(exc)
            return None

    @staticmethod
    def _prefer_qwen(language: Language) -> bool:
        return language is Language.EN

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        backend = self._qwen_backend() if self._prefer_qwen(language) else None
        if backend is not None:
            try:
                yield from backend.stream(text, language=language, voice=voice, style=style)
                return
            except Exception as exc:  # noqa: BLE001 - optional backend fallback
                self._qwen_error = str(exc)
        yield from self.indic.stream(text, language=language, voice=voice, style=style)


def build_streaming_tts():
    engine = os.getenv("TOM_TTS_ENGINE", "hybrid").strip().lower()
    if engine in {"hybrid", "adaptive", "auto"}:
        return HybridExpressiveTTS()
    if engine in {"qwen3", "qwen3-tts", "qwen"}:
        from .qwen3_tts_stream import Qwen3TTSStreamingAdapter

        return Qwen3TTSStreamingAdapter()
    if engine in {"indic-parler", "parler", "indic_parler"}:
        from .indic_parler_stream import IndicParlerStreamingAdapter

        return IndicParlerStreamingAdapter()
    if engine in {"cosyvoice", "cosyvoice3", "cosyvoice2"}:
        from .cosyvoice_stream import CosyVoiceStreamingAdapter

        return CosyVoiceStreamingAdapter()
    raise RuntimeError(f"Unsupported TOM_TTS_ENGINE: {engine}")
