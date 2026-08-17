from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


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
    should_speak: bool = False
    context_keys: tuple[str, ...] = ()
    fingerprint: str = ""


class NotificationIntelligence:
    """Fast local-first notification triage with privacy/risk boundaries.

    The hot path never waits for an LLM. A richer model may consume the
    already-classified event asynchronously, but it cannot lower a sensitive
    notification's safety classification or authorize an action by itself.
    """

    _URGENT = ("urgent", "emergency", "fraud", "security alert", "suspicious login", "account locked")
    _SENSITIVE = ("otp", "verification code", "password", "bank", "upi", "cvv", "card", "one time password")
    _ACTIONABLE = ("meeting", "calendar", "flight", "delivery", "appointment", "message", "missed call", "call")
    _SOCIAL = ("whatsapp", "instagram", "telegram", "messenger", "sms", "gmail", "email")

    def __init__(self, authorized_packages: set[str] | None = None, *, speak_background: bool = False) -> None:
        self.authorized_packages = set(authorized_packages or ())
        self.speak_background = speak_background
        self._seen: dict[str, float] = {}

    def classify(self, event: NotificationEvent, *, now: float | None = None) -> NotificationDecision:
        now = time.time() if now is None else now
        title = event.title.strip()
        text = event.text.strip()
        blob = f"{title} {text}".casefold()
        fingerprint = hashlib.sha256(f"{event.package}|{title}|{text}".encode()).hexdigest()[:20]

        # Deduplicate noisy reposts for a short window without losing urgency.
        duplicate = fingerprint in self._seen and now - self._seen[fingerprint] < 30.0
        self._seen[fingerprint] = now
        sensitive = any(word in blob for word in self._SENSITIVE)
        urgent = any(word in blob for word in self._URGENT)
        actionable = any(word in blob for word in self._ACTIONABLE)
        social = any(word in event.package.casefold() or word in blob for word in self._SOCIAL)
        authorized = not self.authorized_packages or event.package in self.authorized_packages

        if not title and not text:
            return NotificationDecision(NotificationPriority.IGNORE, "empty notification", fingerprint=fingerprint)
        if duplicate and not urgent:
            return NotificationDecision(NotificationPriority.BACKGROUND, "duplicate notification suppressed", fingerprint=fingerprint)
        if sensitive:
            return NotificationDecision(
                NotificationPriority.RELEVANT,
                "sensitive notification; surface without exposing secrets and never act automatically",
                requires_user_confirmation=True,
                should_speak=authorized,
                context_keys=("sender", "app", "sensitive_type"),
                fingerprint=fingerprint,
            )
        if urgent:
            return NotificationDecision(
                NotificationPriority.URGENT,
                "urgent/security language detected",
                should_speak=authorized,
                context_keys=("sender", "app", "content", "urgency"),
                fingerprint=fingerprint,
            )
        if actionable:
            return NotificationDecision(
                NotificationPriority.RELEVANT,
                "actionable context detected",
                suggested_action="inspect_context",
                should_speak=authorized,
                context_keys=("sender", "app", "content", "deadline", "action_type"),
                fingerprint=fingerprint,
            )
        if social:
            return NotificationDecision(
                NotificationPriority.RELEVANT,
                "social notification",
                should_speak=authorized,
                context_keys=("sender", "app", "content"),
                fingerprint=fingerprint,
            )
        return NotificationDecision(
            NotificationPriority.BACKGROUND,
            "non-urgent notification queued silently",
            should_speak=self.speak_background and authorized,
            context_keys=("app",),
            fingerprint=fingerprint,
        )

    def triage_payload(self, event: NotificationEvent, *, now: float | None = None) -> dict[str, Any]:
        decision = self.classify(event, now=now)
        return {
            "package": event.package,
            "notification_id": event.notification_id,
            "priority": decision.priority.value,
            "reason": decision.reason,
            "suggested_action": decision.suggested_action,
            "requires_user_confirmation": decision.requires_user_confirmation,
            "should_speak": decision.should_speak,
            "context_keys": list(decision.context_keys),
            "fingerprint": decision.fingerprint,
        }
