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
    SPEAKERS = {
        "tom_m1": "Ryan",
        "tom_m2": "Aiden",
        "tom_f1": "Serena",
    }

    def __init__(self) -> None:
        self.client = Client(self.SPACE)

    @staticmethod
    def _language(language: Language) -> str:
        if language in {Language.EN, Language.HINGLISH}:
            return "English"
        raise RuntimeError("Qwen3 CustomVoice Space currently supports English only")

    @staticmethod
    def _instruction(style: VoiceStyle) -> str:
        emotion = getattr(style.emotion, "value", str(style.emotion))
        rate = getattr(style, "speaking_rate", 1.0)
        speed = (
            "moderately fast"
            if rate > 1.1
            else "slow and relaxed"
            if rate < 0.9
            else "natural conversational"
        )
        return (
            f"Speak in a {emotion} tone, with {speed} pacing, natural pauses, "
            "clear pronunciation, and warm conversational delivery."
        )

    def _generate(
        self,
        text: str,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> Path:
        speaker = self.SPEAKERS.get(voice.id, "Ryan")
        audio, status = self.client.predict(
            text=text,
            language=self._language(language),
            speaker=speaker,
            instruct=self._instruction(style),
            api_name="/generate_custom_voice",
        )

        if not audio:
            raise RuntimeError(f"Qwen ZeroGPU Space returned no audio. Status={status}")

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
                f"Unexpected Qwen audio format: channels={channels}, sample_width={sample_width}"
            )

        bytes_per_chunk = int(sample_rate * self.CHUNK_MS / 1000) * 2
        for i in range(0, len(pcm), bytes_per_chunk):
            yield TTSChunk(
                pcm16=pcm[i:i + bytes_per_chunk],
                sample_rate=sample_rate,
            )


def build_qwen_space_tts() -> QwenSpaceTTS:
    return QwenSpaceTTS()
