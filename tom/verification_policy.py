from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .success_predicates import ActionKind


class VerificationMode(str, Enum):
    STANDARD = "standard"
    STRICT = "strict"
    AUTHORITATIVE = "authoritative"


@dataclass(frozen=True)
class VerificationRequirements:
    mode: VerificationMode
    confidence_threshold: float
    timeout_ms: int
    poll_interval_ms: int
    stability_window_ms: int
    require_authoritative: bool = False


class VerificationPolicy:
    """Converts action risk into deterministic verification requirements."""

    def requirements(self, kind: str, risk: str = "reversible") -> VerificationRequirements:
        normalized = kind.lower().strip()
        if normalized in {ActionKind.PAYMENT.value, ActionKind.UPI.value} or risk == "consequent":
            return VerificationRequirements(
                VerificationMode.AUTHORITATIVE,
                0.98,
                10000,
                250,
                600,
                require_authoritative=True,
            )
        if normalized in {ActionKind.SEARCH.value, ActionKind.OPEN_URL.value}:
            return VerificationRequirements(VerificationMode.STRICT, 0.90, 7000, 250, 500)
        if normalized in {ActionKind.OPEN_APP.value, ActionKind.TAP.value, ActionKind.TAP_NODE.value}:
            return VerificationRequirements(VerificationMode.STRICT, 0.85, 5000, 250, 400)
        return VerificationRequirements(VerificationMode.STANDARD, 0.80, 5000, 250, 400)

    def accept(self, result_state: str, confidence: float, *, requirements: VerificationRequirements, authoritative: bool = False) -> bool:
        if result_state != "verified":
            return False
        if confidence < requirements.confidence_threshold:
            return False
        if requirements.require_authoritative and not authoritative:
            return False
        return True
