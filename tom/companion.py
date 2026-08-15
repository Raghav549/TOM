from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class CompanionProfile:
    """User-controlled personality and conversation preferences."""

    name: str = "TOM"
    interests: set[str] = field(default_factory=set)
    style: str = "friendly"
    language: str = "auto"
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
        return (
            f"You are {self.name}, a friendly personal AI companion. "
            f"Conversation style: {self.style}. Language: {self.language}. "
            f"User interests: {interests}. Preferred airlines: {airlines}. Preferred places: {places}. "
            f"Budget: {self.budget_currency} {self.budget_limit if self.budget_limit is not None else 'not set'}. "
            "Speak naturally and briefly while acting. Mention useful discoveries as they happen. "
            "Never fabricate observations, prices, bookings, payments, messages, or completed actions."
        )

    def progress_line(self, text: str) -> str:
        if not self.commentary_enabled:
            return ""
        return text.strip()

    def set_interests(self, interests: Iterable[str]) -> None:
        self.interests = {item.strip() for item in interests if item.strip()}

    def set_preferred_airlines(self, airlines: Iterable[str]) -> None:
        self.preferred_airlines = [item.strip() for item in airlines if item.strip()]

    def set_preferred_places(self, places: Iterable[str]) -> None:
        self.preferred_places = [item.strip() for item in places if item.strip()]
