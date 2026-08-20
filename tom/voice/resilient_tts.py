from __future__ import annotations

import logging
from typing import Iterator

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle

log = logging.getLogger(__name__)


class ResilientTTS:
    """
    TOM resilient voice backend.

    Primary:
        Qwen3-TTS Hugging Face Space

    Fallback:
        Indic Parler-TTS

    The fallback is only invoked when the primary backend fails
    before/during synthesis.
    """

    def __init__(self) -> None:
        from .qwen_space_stream import QwenSpaceTTS
        from .indic_parler_stream import IndicParlerStreamingAdapter

        self.primary = QwenSpaceTTS()
        self.fallback = IndicParlerStreamingAdapter()
        self.qwen = self.primary
        self.indic = self.fallback

        self.primary_name = "qwen-space"
        self.fallback_name = "indic-parler"
        self.last_backend: str | None = None

    def stream(
        self,
        text: str,
        *,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> Iterator[TTSChunk]:

        # PRIMARY: Qwen remote ZeroGPU
        try:
            primary = getattr(self, "primary", None) or getattr(self, "qwen", None)
            fallback = getattr(self, "fallback", None) or getattr(self, "indic", None)
            primary_name = getattr(self, "primary_name", "qwen-space")
            fallback_name = getattr(self, "fallback_name", "indic-parler")
            log.info("TOM TTS primary backend: %s", primary_name)

            chunks = list(
                primary.stream(
                    text,
                    language=language,
                    voice=voice,
                    style=style,
                )
            )

            if chunks:
                log.info(
                    "TOM TTS primary succeeded: %d chunks",
                    len(chunks),
                )
                self.last_backend = primary_name

                for chunk in chunks:
                    yield chunk

                return

            raise RuntimeError("Qwen returned zero audio")

        except Exception as primary_error:
            log.warning(
                "Qwen TTS failed; switching to %s: %s",
                getattr(self, "fallback_name", "indic-parler"),
                primary_error,
            )

        # FALLBACK: Indic Parler-TTS
        try:
            log.info(
                "TOM TTS fallback backend: %s",
                getattr(self, "fallback_name", "indic-parler"),
            )

            chunks = list(
                fallback.stream(
                    text,
                    language=language,
                    voice=voice,
                    style=style,
                )
            )

            if not chunks:
                raise RuntimeError("Indic Parler returned zero audio")

            log.info(
                "TOM TTS fallback succeeded: %d chunks",
                len(chunks),
            )
            self.last_backend = getattr(self, "fallback_name", "indic-parler")

            for chunk in chunks:
                yield chunk

        except Exception as fallback_error:
            raise RuntimeError(
                "All TOM TTS backends failed. "
                f"Primary={getattr(self, 'primary_name', 'qwen-space')}; "
                f"Fallback={getattr(self, 'fallback_name', 'indic-parler')}; "
                f"fallback_error={fallback_error}"
            ) from fallback_error


def build_resilient_tts() -> ResilientTTS:
    return ResilientTTS()
