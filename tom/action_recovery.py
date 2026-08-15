from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecoveryDecision(str, Enum):
    RETRY = "retry"
    REGROUND = "re_ground"
    FALLBACK = "fallback"
    ASK_USER = "ask_user"
    STOP = "stop"


@dataclass(frozen=True)
class RecoveryPolicy:
    max_attempts: int = 2
    confidence_floor: float = 0.65

    def decide(
        self,
        *,
        attempt: int,
        target_confidence: float,
        action_completed: bool,
        verification_passed: bool,
        fallback_available: bool,
    ) -> RecoveryDecision:
        if verification_passed:
            return RecoveryDecision.STOP
        if action_completed and not verification_passed:
            return RecoveryDecision.REGROUND if target_confidence >= self.confidence_floor else RecoveryDecision.ASK_USER
        if target_confidence < self.confidence_floor:
            return RecoveryDecision.REGROUND if attempt < self.max_attempts else RecoveryDecision.ASK_USER
        if attempt < self.max_attempts:
            return RecoveryDecision.RETRY
        if fallback_available:
            return RecoveryDecision.FALLBACK
        return RecoveryDecision.ASK_USER
