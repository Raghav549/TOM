from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class CompanionProfile:
    """User-controlled personality and conversation preferences."""

    name: str = "Tom"
    interests: set[str] = field(default_factory=set)
    style: str = "friendly"
    language: str = "auto"
    commentary_enabled: bool = True
    commentary_interval_seconds: float = 18.0

    def system_hint(self) -> str:
        interests = ", ".join(sorted(self.interests)) or "none configured"
        return (
            f"You are {self.name}, a friendly personal AI companion. "
            f"Conversation style: {self.style}. Language: {self.language}. "
            f"User interests: {interests}. "
            "Be concise while acting. Offer occasional context-aware comments only when useful; "
            "never fabricate observations or claim actions you did not perform."
        )

    def set_interests(self, interests: Iterable[str]) -> None:
        self.interests = {item.strip() for item in interests if item.strip()}
