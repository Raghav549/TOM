from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class CompanionProfile:
    """User-controlled personality, identity and voice-character preferences."""

    name: str = "TOM"
    interests: set[str] = field(default_factory=set)
    style: str = "friendly+sigma"
    traits: list[str] = field(default_factory=lambda: ["helpful", "warm", "confident"])
    language: str = "auto"
    voice_id: str = "tom_m1"
    pitch_shift: float | None = None
    speaking_rate: float | None = None
    warmth: float | None = None
    breathiness: float | None = None
    expressiveness: float | None = None
    commentary_enabled: bool = True
    commentary_interval_seconds: float = 18.0
    budget_currency: str = "INR"
    budget_limit: float | None = None
    preferred_airlines: list[str] = field(default_factory=list)
    preferred_places: list[str] = field(default_factory=list)

    def system_hint(self) -> str:
        interests = ", ".join(sorted(self.interests)) or "none configured"
        airlines = ", ".join(self.preferred_airlines) or "none configured"
        places = ", ".join(self.preferred_places) or "none configured"
        traits = ", ".join(self.traits) or "none configured"
        return (
            f"You are {self.name}, a personal AI companion. Conversation style: {self.style}. "
            f"Character traits: {traits}. Language: {self.language}. "
            f"Voice profile: {self.voice_id}. User interests: {interests}. "
            f"Preferred airlines: {airlines}. Preferred places: {places}. "
            f"Budget: {self.budget_currency} {self.budget_limit if self.budget_limit is not None else 'not set'}. "
            "Speak naturally and briefly while acting. Mention useful discoveries as they happen. "
            "Never fabricate observations, prices, bookings, payments, messages, or completed actions."
        )

    def progress_line(self, text: str) -> str:
        if not self.commentary_enabled:
            return ""
        return text.strip()

    def set_identity(self, *, name: str | None = None, style: str | None = None,
                     traits: Iterable[str] | None = None) -> None:
        if name is not None:
            self.name = name.strip()[:64] or "TOM"
        if style is not None:
            self.style = style.strip()[:64] or "friendly+sigma"
        if traits is not None:
            self.traits = [item.strip()[:48] for item in traits if item.strip()][:12]

    def set_voice_controls(self, *, voice_id: str | None = None, pitch_shift: float | None = None,
                           speaking_rate: float | None = None, warmth: float | None = None,
                           breathiness: float | None = None, expressiveness: float | None = None) -> None:
        if voice_id is not None:
            self.voice_id = voice_id.strip() or "tom_m1"
        self.pitch_shift = pitch_shift
        self.speaking_rate = speaking_rate
        self.warmth = warmth
        self.breathiness = breathiness
        self.expressiveness = expressiveness

    def set_interests(self, interests: Iterable[str]) -> None:
        self.interests = {item.strip() for item in interests if item.strip()}

    def set_preferred_airlines(self, airlines: Iterable[str]) -> None:
        self.preferred_airlines = [item.strip() for item in airlines if item.strip()]

    def set_preferred_places(self, places: Iterable[str]) -> None:
        self.preferred_places = [item.strip() for item in places if item.strip()]
