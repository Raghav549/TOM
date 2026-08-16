from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Emotion, Language, VoiceStyle


@dataclass(frozen=True)
class ConversationSignals:
    """Signals produced by TOM's semantic/audio context layers."""

    user_text: str = ""
    situation: str = ""
    urgency: float = 0.0
    user_valence: float = 0.0
    user_arousal: float = 0.0
    is_interruption: bool = False
    task_running: bool = False
    task_succeeded: bool = False
    task_failed: bool = False
    user_is_sad: bool = False
    user_is_excited: bool = False
    character_name: str = "TOM"
    character_style: str = "friendly"
    character_traits: tuple[str, ...] = ()
    character_pitch_shift: float | None = None
    character_speaking_rate: float | None = None
    character_warmth: float | None = None
    character_breathiness: float | None = None
    character_expressiveness: float | None = None


class VoiceDirector:
    """Maps conversational context and user character settings to prosody."""

    _hinglish = re.compile(r"\b(bhai|yaar|acha|accha|haan|nahi|matlab|chalo|dekho)\b", re.IGNORECASE)
    _happy = re.compile(r"\b(great|awesome|yay|nice|mast|sahi|wah|haha|lol)\b", re.IGNORECASE)
    _sad = re.compile(r"\b(sad|upset|hurt|dukhi|pareshan|rona|ro raha|ro rahi)\b", re.IGNORECASE)

    def detect_language(self, text: str) -> Language:
        if not text.strip():
            return Language.EN
        devanagari = sum("\u0900" <= ch <= "\u097f" for ch in text)
        bengali = sum("\u0980" <= ch <= "\u09ff" for ch in text)
        latin = sum(ch.isalpha() and ch.isascii() for ch in text)
        if bengali > 2:
            return Language.BN
        if devanagari > 2 and latin > 2:
            return Language.HINGLISH
        if devanagari > 2:
            return Language.HI
        if self._hinglish.search(text):
            return Language.HINGLISH
        return Language.EN

    def direct(self, signals: ConversationSignals) -> VoiceStyle:
        text = signals.user_text
        if signals.task_failed or "error" in signals.situation.lower():
            style = VoiceStyle(emotion=Emotion.CONCERNED, intensity=0.48, speaking_rate=0.96, warmth=0.7,
                               pause_scale=1.12, style_reason="task failure: slower, warm, solution-focused delivery")
        elif signals.task_succeeded:
            style = VoiceStyle(emotion=Emotion.HAPPY, intensity=0.58, speaking_rate=1.04, warmth=0.78,
                               laugh_probability=0.08, style_reason="task success: brief natural positive lift")
        elif signals.user_is_sad or self._sad.search(text):
            style = VoiceStyle(emotion=Emotion.EMPATHETIC, intensity=0.35, speaking_rate=0.90, warmth=0.9,
                               pause_scale=1.25, style_reason="sadness cue: calm empathetic delivery")
        elif signals.user_is_excited or self._happy.search(text):
            style = VoiceStyle(emotion=Emotion.AMUSED, intensity=0.62, speaking_rate=1.08, warmth=0.78,
                               style_reason="positive cue: energetic but restrained delivery")
        elif signals.urgency >= 0.8:
            style = VoiceStyle(emotion=Emotion.SERIOUS, intensity=0.55, speaking_rate=1.08, pause_scale=0.82,
                               style_reason="high urgency: concise delivery")
        elif signals.task_running:
            style = VoiceStyle(emotion=Emotion.WARM, intensity=0.32, speaking_rate=0.98, warmth=0.8,
                               backchannel=True, style_reason="long-running task: short natural progress commentary")
        elif signals.is_interruption:
            style = VoiceStyle(emotion=Emotion.CALM, intensity=0.25, speaking_rate=1.0, pause_scale=0.8,
                               style_reason="interruption: fast turn handoff")
        else:
            style = VoiceStyle(emotion=Emotion.WARM, intensity=0.4, speaking_rate=1.0, warmth=0.65,
                               style_reason="default companion delivery")

        # Character settings are a controlled layer over the situation-aware director.
        style = style.model_copy(update={
            "pitch_shift": signals.character_pitch_shift if signals.character_pitch_shift is not None else style.pitch_shift,
            "speaking_rate": signals.character_speaking_rate if signals.character_speaking_rate is not None else style.speaking_rate,
            "warmth": signals.character_warmth if signals.character_warmth is not None else style.warmth,
            "breathiness": signals.character_breathiness if signals.character_breathiness is not None else style.breathiness,
            "intensity": signals.character_expressiveness if signals.character_expressiveness is not None else style.intensity,
        })
        return style
