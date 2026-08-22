from __future__ import annotations

import io
import wave
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

    def __init__(self, engine: SpeechEngine | object, director: VoiceDirector | None = None, planner: ExpressiveSpeechPlanner | None = None) -> None:
        self.engine = engine
        self.director = director or VoiceDirector()
        self.planner = planner or ExpressiveSpeechPlanner()

    def prepare_turn(self, text: str, *, voice_id: str = "tom_m1", signals: ConversationSignals | None = None) -> VoiceTurn:
        if voice_id not in VOICE_PROFILES:
            raise ValueError(f"Unknown TOM voice profile: {voice_id}")
        signals = signals or ConversationSignals(user_text=text)
        language = self.director.detect_language(text)
        style = self.director.direct(signals)
        plan = self.planner.plan(text, emotion=style.emotion.value, intensity=style.intensity, speaking_rate=style.speaking_rate, warmth=style.warmth)
        style = style.model_copy(update={"prosody_plan": {
            "cues": [cue.__dict__ for cue in plan.cues],
            "pitch_curve": list(plan.pitch_curve),
            "energy_curve": list(plan.energy_curve),
            "rate_curve": list(plan.rate_curve),
            "rationale": list(plan.rationale),
            "character": signals.character_name,
            "character_style": signals.character_style,
            "character_traits": list(signals.character_traits),
            "voice_design": bool(signals.character_traits) and signals.character_style not in {"friendly", "sigma", "default", "friendly+sigma"},
            "temperature": 0.62 if style.intensity < 0.65 else 0.68,
            "top_p": 0.90,
        }})
        return VoiceTurn(text=text, language=language, voice_id=voice_id, style=style)

    def synthesize(self, turn: VoiceTurn) -> bytes:
        voice = VOICE_PROFILES[turn.voice_id]
        synthesize = getattr(self.engine, "synthesize", None)
        if callable(synthesize):
            return synthesize(turn.text, language=turn.language, voice=voice, style=turn.style)
        stream = getattr(self.engine, "stream", None)
        if not callable(stream):
            raise TypeError("Configured TOM voice engine exposes neither synthesize() nor stream()")
        chunks = list(stream(turn.text, language=turn.language, voice=voice, style=turn.style))
        if not chunks:
            raise RuntimeError("TOM voice engine produced no audio")
        pcm = b"".join(bytes(getattr(chunk, "pcm16", chunk)) for chunk in chunks)
        sample_rate = int(getattr(chunks[0], "sample_rate", 24_000))
        return self._pcm16_wav(pcm, sample_rate)

    @staticmethod
    def _pcm16_wav(pcm: bytes, sample_rate: int) -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return output.getvalue()

    @staticmethod
    def chunks(audio: bytes, chunk_size: int = 32_768) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        for offset in range(0, len(audio), chunk_size):
            yield audio[offset : offset + chunk_size]
