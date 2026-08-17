from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class NotificationRelevance(StrEnum):
    IMPORTANT = "important"
    ACTIONABLE = "actionable"
    INFORMATIONAL = "informational"
    LOW_VALUE = "low_value"
    PRIVATE = "private"


@dataclass(frozen=True)
class NotificationDecision:
    relevance: NotificationRelevance
    speak: bool
    summary: str
    reason: str
    requires_user_confirmation: bool = False


class NotificationIntelligence:
    """Fast first-pass triage; never executes consequential actions automatically."""

    IMPORTANT_CATEGORIES = {"call", "message", "alarm", "missed_call", "email"}
    LOW_VALUE_CATEGORIES = {"progress", "system", "marketing", "promotion", "silent"}
    ACTION_WORDS = ("urgent", "important", "otp", "verification", "meeting", "interview", "payment", "refund", "security")

    def classify(self, notification: Mapping[str, Any], *, privacy_mode: bool = False) -> NotificationDecision:
        package = str(notification.get("package", "")).casefold()
        category = str(notification.get("category", "")).casefold()
        title = str(notification.get("title", ""))
        text = str(notification.get("text", notification.get("big_text", "")))
        blob = f"{title} {text}".casefold()
        if privacy_mode:
            return NotificationDecision(NotificationRelevance.PRIVATE, False, "A private notification arrived.", "privacy mode")
        if any(word in blob for word in self.ACTION_WORDS) or category in self.IMPORTANT_CATEGORIES:
            return NotificationDecision(NotificationRelevance.ACTIONABLE, True, self._summary(title, text), "high-signal notification")
        if category in self.LOW_VALUE_CATEGORIES:
            return NotificationDecision(NotificationRelevance.LOW_VALUE, False, "", "low-value notification")
        if any(marker in package for marker in ("whatsapp", "telegram", "signal", "messenger", "gmail", "phone")):
            return NotificationDecision(NotificationRelevance.INFORMATIONAL, True, self._summary(title, text), "communication notification")
        return NotificationDecision(NotificationRelevance.INFORMATIONAL, False, self._summary(title, text), "default quiet policy")

    @staticmethod
    def _summary(title: str, text: str) -> str:
        if title and text:
            return f"{title}: {text[:220]}"
        return (title or text)[:220]

    def user_facing_commentary(self, decision: NotificationDecision) -> str:
        if not decision.speak:
            return ""
        if decision.relevance is NotificationRelevance.ACTIONABLE:
            return f"Bhai, ek important notification aayi hai. Main dekh raha hoon — {decision.summary}"
        return f"Bhai, ek notification aayi hai — {decision.summary}"
