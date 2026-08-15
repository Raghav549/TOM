from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
import uuid


class RiskLevel(str, Enum):
    READ = "read"
    REVERSIBLE = "reversible"
    CONSEQUENT = "consequent"


CONSEQUENT_ACTIONS = frozenset(
    {
        "send_message",
        "send_email",
        "send_sms",
        "send_form",
        "purchase",
        "payment",
        "book",
        "cancel_booking",
        "delete",
        "account_change",
        "publish",
        "share_sensitive_data",
    }
)


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    risk: RiskLevel
    reason: str
    confirmation_required: bool = False


@dataclass(frozen=True)
class ConfirmationToken:
    token: str
    task_id: str
    action_id: str
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at


class ActionPolicy:
    """Fail-closed policy for actions with real-world consequences."""

    def classify(self, action: str) -> RiskLevel:
        normalized = action.strip().lower()
        if normalized in CONSEQUENT_ACTIONS:
            return RiskLevel.CONSEQUENT
        if normalized in {"back", "home", "recents", "scroll", "swipe", "tap", "tap_node", "open_app", "open_url"}:
            return RiskLevel.REVERSIBLE
        return RiskLevel.READ

    def decide(self, action: str, *, explicit_confirmation: bool = False) -> ActionDecision:
        risk = self.classify(action)
        if risk is RiskLevel.CONSEQUENT and not explicit_confirmation:
            return ActionDecision(
                allowed=False,
                risk=risk,
                reason="explicit confirmation required immediately before consequential action",
                confirmation_required=True,
            )
        return ActionDecision(True, risk, "policy allows action")

    def issue_confirmation(self, task_id: str, action_id: str, ttl_seconds: float = 60.0) -> ConfirmationToken:
        if not task_id or not action_id:
            raise ValueError("task_id and action_id are required")
        return ConfirmationToken(
            token=uuid.uuid4().hex,
            task_id=task_id,
            action_id=action_id,
            expires_at=time.time() + ttl_seconds,
        )

    def validate_confirmation(self, token: ConfirmationToken, task_id: str, action_id: str) -> bool:
        return (
            not token.expired
            and token.task_id == task_id
            and token.action_id == action_id
            and bool(token.token)
        )
