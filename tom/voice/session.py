from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .director import ConversationSignals, VoiceDirector
from .engine import SpeechEngine
from .models import VOICE_PROFILES, Language, VoiceStyle


@dataclass
class VoiceTurn:
    text: str
    language: Language
    voice_id: str
    style: VoiceStyle


class VoiceSession:
    """Coordinates language detection, emotional direction and synthesis."""

    def __init__(self, engine: SpeechEngine, director: VoiceDirector | None = None) -> None:
        self.engine = engine
        self.director = director or VoiceDirector()

    def prepare_turn(
        self,
        text: str,
        *,
        voice_id: str = "tom_m1",
        signals: ConversationSignals | None = None,
    ) -> VoiceTurn:
        if voice_id not in VOICE_PROFILES:
            raise ValueError(f"Unknown TOM voice profile: {voice_id}")
        language = self.director.detect_language(text)
        style = self.director.direct(signals or ConversationSignals(user_text=text))
        return VoiceTurn(text=text, language=language, voice_id=voice_id, style=style)

    def synthesize(self, turn: VoiceTurn) -> bytes:
        voice = VOICE_PROFILES[turn.voice_id]
        return self.engine.synthesize(
            turn.text,
            language=turn.language,
            voice=voice,
            style=turn.style,
        )

    @staticmethod
    def chunks(audio: bytes, chunk_size: int = 32_768) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        for offset in range(0, len(audio), chunk_size):
            yield audio[offset : offset + chunk_size]
