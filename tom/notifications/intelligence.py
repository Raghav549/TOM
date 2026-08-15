from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class NotificationPriority(str, Enum):
    IGNORE = "ignore"
    BACKGROUND = "background"
    RELEVANT = "relevant"
    URGENT = "urgent"


@dataclass(frozen=True)
class NotificationEvent:
    package: str
    title: str
    text: str
    notification_id: str
    extras: dict[str, Any] | None = None


@dataclass(frozen=True)
class NotificationDecision:
    priority: NotificationPriority
    reason: str
    suggested_action: str | None = None
    requires_user_confirmation: bool = False


class NotificationIntelligence:
    """Deterministic safety-first classifier; an LLM can enrich it later."""

    def classify(self, event: NotificationEvent) -> NotificationDecision:
        text = f"{event.title} {event.text}".lower()
        sensitive = any(word in text for word in ("otp", "verification code", "password", "bank", "upi"))
        urgent = any(word in text for word in ("urgent", "emergency", "fraud", "security alert"))

        if sensitive:
            return NotificationDecision(
                NotificationPriority.RELEVANT,
                "sensitive notification; never act automatically",
                requires_user_confirmation=True,
            )
        if urgent:
            return NotificationDecision(NotificationPriority.URGENT, "urgent language detected")
        if not event.title.strip() and not event.text.strip():
            return NotificationDecision(NotificationPriority.IGNORE, "empty notification")
        return NotificationDecision(NotificationPriority.RELEVANT, "potentially useful notification")
