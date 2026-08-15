from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Language(str, Enum):
    HI = "hi"
    EN = "en"
    HINGLISH = "hinglish"
    BN = "bn"


class Emotion(str, Enum):
    NEUTRAL = "neutral"
    WARM = "warm"
    HAPPY = "happy"
    AMUSED = "amused"
    EMPATHETIC = "empathetic"
    CONCERNED = "concerned"
    EXCITED = "excited"
    CALM = "calm"
    APOLOGETIC = "apologetic"
    CURIOUS = "curious"
    SURPRISED = "surprised"
    SERIOUS = "serious"


class VoiceProfile(BaseModel):
    id: str
    label: str
    gender: str
    reference_audio: str | None = None
    description: str
    supported_languages: tuple[Language, ...] = (
        Language.HI,
        Language.EN,
        Language.HINGLISH,
        Language.BN,
    )


class VoiceStyle(BaseModel):
    emotion: Emotion = Emotion.NEUTRAL
    intensity: float = Field(default=0.45, ge=0.0, le=1.0)
    speaking_rate: float = Field(default=1.0, ge=0.65, le=1.35)
    pitch_shift: float = Field(default=0.0, ge=-1.0, le=1.0)
    warmth: float = Field(default=0.55, ge=0.0, le=1.0)
    pause_scale: float = Field(default=1.0, ge=0.5, le=2.0)
    breathiness: float = Field(default=0.15, ge=0.0, le=1.0)
    laugh_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    backchannel: bool = False
    style_reason: str = ""


VOICE_PROFILES: dict[str, VoiceProfile] = {
    "tom_m1": VoiceProfile(
        id="tom_m1",
        label="Tom M1",
        gender="male",
        description="Low-mid, grounded, friendly conversational male voice.",
    ),
    "tom_m2": VoiceProfile(
        id="tom_m2",
        label="Tom M2",
        gender="male",
        description="Brighter, quicker, playful conversational male voice.",
    ),
    "tom_f1": VoiceProfile(
        id="tom_f1",
        label="Tom F1",
        gender="female",
        description="Warm, clear, expressive conversational female voice.",
    ),
}
