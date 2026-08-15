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


class VoiceDirector:
    """Maps conversational context to controllable prosody."""

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
            return VoiceStyle(emotion=Emotion.CONCERNED, intensity=0.48, speaking_rate=0.96, warmth=0.7,
                              pause_scale=1.12, style_reason="task failure: slower, warm, solution-focused delivery")
        if signals.task_succeeded:
            return VoiceStyle(emotion=Emotion.HAPPY, intensity=0.58, speaking_rate=1.04, warmth=0.78,
                              laugh_probability=0.08, style_reason="task success: brief natural positive lift")
        if signals.user_is_sad or self._sad.search(text):
            return VoiceStyle(emotion=Emotion.EMPATHETIC, intensity=0.35, speaking_rate=0.90, warmth=0.9,
                              pause_scale=1.25, style_reason="sadness cue: calm empathetic delivery")
        if signals.user_is_excited or self._happy.search(text):
            return VoiceStyle(emotion=Emotion.AMUSED, intensity=0.62, speaking_rate=1.08, warmth=0.78,
                              style_reason="positive cue: energetic but restrained delivery")
        if signals.urgency >= 0.8:
            return VoiceStyle(emotion=Emotion.SERIOUS, intensity=0.55, speaking_rate=1.08, pause_scale=0.82,
                              style_reason="high urgency: concise delivery")
        if signals.task_running:
            return VoiceStyle(emotion=Emotion.WARM, intensity=0.32, speaking_rate=0.98, warmth=0.8,
                              backchannel=True, style_reason="long-running task: short natural progress commentary")
        if signals.is_interruption:
            return VoiceStyle(emotion=Emotion.CALM, intensity=0.25, speaking_rate=1.0, pause_scale=0.8,
                              style_reason="interruption: fast turn handoff")
        return VoiceStyle(emotion=Emotion.WARM, intensity=0.4, speaking_rate=1.0, warmth=0.65,
                          style_reason="default companion delivery")
