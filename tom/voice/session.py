from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from .director import ConversationSignals, VoiceDirector
from .engine import SpeechEngine
from .models import VOICE_PROFILES, Language, VoiceStyle
from .prosody import ExpressiveSpeechPlanner


@dataclass
class VoiceTurn:
    text: str
    language: Language
    voice_id: str
    style: VoiceStyle


class VoiceSession:
    """Coordinates language, emotion, character identity, expressive prosody and synthesis."""

    def __init__(self, engine: SpeechEngine, director: VoiceDirector | None = None, planner: ExpressiveSpeechPlanner | None = None) -> None:
        self.engine = engine
        self.director = director or VoiceDirector()
        self.planner = planner or ExpressiveSpeechPlanner()

    def prepare_turn(self, text: str, *, voice_id: str = "tom_m1", signals: ConversationSignals | None = None) -> VoiceTurn:
        if voice_id not in VOICE_PROFILES:
            raise ValueError(f"Unknown TOM voice profile: {voice_id}")
        signals = signals or ConversationSignals(user_text=text)
        language = self.director.detect_language(text)
        style = self.director.direct(signals)
        plan = self.planner.plan(
            text,
            emotion=style.emotion.value,
            intensity=style.intensity,
            speaking_rate=style.speaking_rate,
            warmth=style.warmth,
        )
        style = style.model_copy(update={"prosody_plan": {
            "cues": [cue.__dict__ for cue in plan.cues],
            "pitch_curve": list(plan.pitch_curve),
            "energy_curve": list(plan.energy_curve),
            "rate_curve": list(plan.rate_curve),
            "rationale": list(plan.rationale),
            "character": signals.character_name,
            "character_style": signals.character_style,
            "character_traits": list(signals.character_traits),
            "voice_design": signals.character_style not in {"friendly", "sigma", "default"} or bool(signals.character_traits),
            "temperature": 0.62 if style.intensity < 0.65 else 0.72,
            "top_p": 0.90,
        }})
        return VoiceTurn(text=text, language=language, voice_id=voice_id, style=style)

    def synthesize(self, turn: VoiceTurn) -> bytes:
        voice = VOICE_PROFILES[turn.voice_id]
        return self.engine.synthesize(turn.text, language=turn.language, voice=voice, style=turn.style)

    @staticmethod
    def chunks(audio: bytes, chunk_size: int = 32_768) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        for offset in range(0, len(audio), chunk_size):
            yield audio[offset : offset + chunk_size]
