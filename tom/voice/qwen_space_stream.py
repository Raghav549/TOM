from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Iterator

from gradio_client import Client

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


class QwenSpaceTTS:
    SPACE = os.getenv("TOM_QWEN_SPACE", "Qwen/Qwen3-TTS")
    CHUNK_MS = 200

    def __init__(self) -> None:
        self.client = Client(self.SPACE)

    @staticmethod
    def _language(language: Language) -> str:
        name = getattr(language, "name", "")
        value = getattr(language, "value", "")

        if name in {"EN", "ENGLISH"} or value in {"en", "English"}:
            return "English"
        if name in {"HI", "HINDI"} or value in {"hi", "Hindi"}:
            return "Hindi"

        return "English"

    @staticmethod
    def _voice_description(
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> str:
        gender = getattr(voice, "gender", "male")
        name = getattr(voice, "name", "Rohit")

        rate = getattr(style, "speaking_rate", 1.0)

        speed = (
            "moderately fast"
            if rate > 1.1
            else "slow and relaxed"
            if rate < 0.9
            else "natural conversational"
        )

        return (
            f"A warm Indian {gender} voice named {name}. "
            f"Natural human conversational delivery, {speed} speaking rate, "
            "clear pronunciation, friendly and intelligent personality, "
            "subtle emotion, natural pauses and realistic breathing. "
            "Do not sound robotic or like a news reader."
        )

    def _generate(
        self,
        text: str,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ):
        audio, status = self.client.predict(
            text=text,
            language=self._language(language),
            voice_description=self._voice_description(voice, style),
            api_name="/generate_voice_design",
        )

        if not audio:
            raise RuntimeError(f"Qwen Space returned no audio. Status={status}")

        return Path(audio)

    def stream(
        self,
        text: str,
        *,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> Iterator[TTSChunk]:

        audio_path = self._generate(text, language, voice, style)

        with wave.open(str(audio_path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            pcm = wav.readframes(wav.getnframes())

        if channels != 1 or sample_width != 2:
            raise RuntimeError(
                f"Unexpected Qwen audio format: "
                f"channels={channels}, sample_width={sample_width}"
            )

        bytes_per_chunk = int(
            sample_rate * self.CHUNK_MS / 1000
        ) * 2

        for i in range(0, len(pcm), bytes_per_chunk):
            yield TTSChunk(
                pcm16=pcm[i:i + bytes_per_chunk],
                sample_rate=sample_rate,
            )


def build_qwen_space_tts() -> QwenSpaceTTS:
    return QwenSpaceTTS()
