from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Mapping

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
    require_terminal_state: bool = False


class VerificationPolicy:
    """Map action semantics/risk to deterministic evidence requirements."""

    _CONSEQUENTIAL: ClassVar[frozenset[str]] = frozenset({
        ActionKind.PAYMENT.value,
        ActionKind.UPI.value,
        ActionKind.SEND.value,
        ActionKind.CALL.value,
        ActionKind.VIDEO_CALL.value,
        ActionKind.FORM_SUBMIT.value,
        ActionKind.UPLOAD.value,
        ActionKind.DOWNLOAD.value,
    })

    def requirements(self, kind: str, risk: str = "reversible") -> VerificationRequirements:
        normalized = kind.lower().strip()
        if normalized in {ActionKind.PAYMENT.value, ActionKind.UPI.value} or risk in {"consequent", "financial"}:
            return VerificationRequirements(VerificationMode.AUTHORITATIVE, 0.98, 10000, 250, 600, True, True)
        if normalized in {ActionKind.SEND.value, ActionKind.FORM_SUBMIT.value}:
            return VerificationRequirements(VerificationMode.STRICT, 0.94, 8000, 250, 500, False, True)
        if normalized in {ActionKind.CALL.value, ActionKind.VIDEO_CALL.value}:
            return VerificationRequirements(VerificationMode.STRICT, 0.92, 8000, 250, 500, False, True)
        if normalized in {ActionKind.SEARCH.value, ActionKind.OPEN_URL.value}:
            return VerificationRequirements(VerificationMode.STRICT, 0.90, 7000, 250, 500)
        if normalized in {ActionKind.OPEN_APP.value, ActionKind.TAP.value, ActionKind.TAP_NODE.value, ActionKind.SELECT.value}:
            return VerificationRequirements(VerificationMode.STRICT, 0.85, 5000, 250, 400)
        if normalized in self._CONSEQUENTIAL:
            return VerificationRequirements(VerificationMode.STRICT, 0.92, 8000, 250, 500, False, True)
        return VerificationRequirements(VerificationMode.STANDARD, 0.80, 5000, 250, 400)

    def accept(
        self,
        result_state: str,
        confidence: float,
        *,
        requirements: VerificationRequirements,
        authoritative: bool = False,
        terminal: bool = True,
    ) -> bool:
        if result_state != "verified" or confidence < requirements.confidence_threshold:
            return False
        if requirements.require_authoritative and not authoritative:
            return False
        if requirements.require_terminal_state and not terminal:
            return False
        return True
