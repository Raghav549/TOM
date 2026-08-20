from __future__ import annotations

import os
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


class Qwen3TTSSpaceAdapter:
    """Resilient non-local Qwen3-TTS Space adapter.

    The official Qwen3-TTS Space exposes Gradio CustomVoice generation. It is
    intentionally treated as a best-effort provider: if the Space/API is down,
    the caller can fall back to TOM's local/open Indic stack instead of faking
    audio. The Space is non-streaming, so TOM chunks the returned 24 kHz WAV.
    """

    DEFAULT_SPACE = "Qwen/Qwen3-TTS"
    SAMPLE_RATE = 24_000
    SUPPORTED: set[Language] = {Language.EN}
    SPEAKERS = {"tom_m1": "Ryan", "tom_m2": "Aiden", "tom_f1": "Serena"}

    def __init__(self) -> None:
        self.space = os.getenv("TOM_QWEN3_TTS_SPACE", self.DEFAULT_SPACE)
        self.model_size = os.getenv("TOM_QWEN3_TTS_SPACE_MODEL_SIZE", "0.6B")
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from gradio_client import Client
            except ImportError as exc:
                raise RuntimeError("gradio-client is required for TOM_QWEN3_TTS_SPACE") from exc
            self._client = Client(self.space)
        return self._client

    @staticmethod
    def _language(language: Language) -> str:
        if language is Language.EN:
            return "English"
        raise RuntimeError(f"Qwen3-TTS Space does not officially expose TOM language '{language.value}'")

    @staticmethod
    def _instruction(style: VoiceStyle) -> str:
        emotion = style.emotion.value
        rate = "slow" if style.speaking_rate < 0.9 else "fast" if style.speaking_rate > 1.1 else "moderate"
        warmth = "warm and intimate" if style.warmth >= 0.7 else "clear and conversational"
        return (
            f"Speak in a {emotion}, {warmth}, natural conversational style at a {rate} rate. "
            "Use realistic pauses and subtle natural breath timing. Avoid robotic cadence, "
            "theatrical overacting, and announcer-style delivery."
        )

    @staticmethod
    def _audio_path(result: Any) -> str:
        audio = result[0] if isinstance(result, (tuple, list)) else result
        if isinstance(audio, dict):
            path = audio.get("path") or audio.get("name") or audio.get("url")
        else:
            path = getattr(audio, "path", None) or getattr(audio, "name", None) or audio
        if not path:
            raise RuntimeError("Qwen3-TTS Space returned no audio file")
        return str(path)

    @staticmethod
    def _pcm_chunks(path: str, chunk_ms: int = 80) -> Iterator[TTSChunk]:
        with wave.open(path, "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise RuntimeError("Qwen3-TTS Space audio must be mono PCM16")
            sample_rate = wav.getframerate()
            chunk_bytes = max(320, int(sample_rate * chunk_ms / 1000) * 2)
            while True:
                pcm = wav.readframes(chunk_bytes // 2)
                if not pcm:
                    break
                yield TTSChunk(pcm16=pcm, sample_rate=sample_rate)

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        prompt = text.strip()
        if not prompt:
            return
        if language not in self.SUPPORTED:
            raise RuntimeError(f"Qwen3-TTS Space does not support {language.value} in its official UI")
        speaker = self.SPEAKERS.get(voice.id, "Ryan")
        result = self._get_client().predict(
            prompt,
            self._language(language),
            speaker,
            self._instruction(style),
            self.model_size,
            api_name="/generate_custom_voice",
        )
        path = self._audio_path(result)
        try:
            yield from self._pcm_chunks(path)
        finally:
            local = Path(path)
            if local.is_file() and str(local).startswith("/tmp/"):
                try:
                    local.unlink()
                except OSError:
                    pass
