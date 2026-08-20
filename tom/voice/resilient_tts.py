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

        self.qwen = QwenSpaceTTS()
        self.indic = IndicParlerStreamingAdapter()

        self.primary_name = "QwenSpaceTTS"
        self.fallback_name = "IndicParlerTTS"

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
            log.info("TOM TTS primary backend: %s", self.primary_name)

            chunks = list(
                self.qwen.stream(
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

                for chunk in chunks:
                    yield chunk

                return

            raise RuntimeError("Qwen returned zero audio")

        except Exception as primary_error:
            log.warning(
                "Qwen TTS failed; switching to %s: %s",
                self.fallback_name,
                primary_error,
            )

        # FALLBACK: Indic Parler-TTS
        try:
            log.info(
                "TOM TTS fallback backend: %s",
                self.fallback_name,
            )

            chunks = list(
                self.indic.stream(
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

            for chunk in chunks:
                yield chunk

        except Exception as fallback_error:
            raise RuntimeError(
                "All TOM TTS backends failed. "
                f"Primary=QwenSpaceTTS; Fallback=IndicParlerTTS; "
                f"fallback_error={fallback_error}"
            ) from fallback_error


def build_resilient_tts() -> ResilientTTS:
    return ResilientTTS()
