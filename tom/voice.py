from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    name: str
    gender: VoiceGender
    locale: str = "en-IN"
    style: str = "natural"


VOICES = (
    VoiceProfile("tom-male-1", "Tom One", VoiceGender.MALE),
    VoiceProfile("tom-male-2", "Tom Two", VoiceGender.MALE),
    VoiceProfile("tom-female-1", "Tom One Female", VoiceGender.FEMALE),
)


class SpeechToText:
    async def transcribe(self, audio: bytes, *, locale: str = "en-IN") -> str:
        raise NotImplementedError("STT provider adapter is not configured")


class TextToSpeech:
    async def synthesize(self, text: str, voice: VoiceProfile, *, emotion: str = "neutral") -> bytes:
        raise NotImplementedError("TTS provider adapter is not configured")
