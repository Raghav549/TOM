from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .multimodal_observation import MultimodalObservation


@dataclass(frozen=True)
class VerificationResult:
    status: str  # verified | failed | unknown
    confidence: float
    evidence: tuple[str, ...]


class ActionVerifier:
    """Never equates transport ACK with successful UI state change."""

    def verify(
        self,
        before: MultimodalObservation,
        after: MultimodalObservation | None,
        predicate: Callable[[MultimodalObservation], bool],
    ) -> VerificationResult:
        if after is None:
            return VerificationResult("unknown", 0.0, ("post_action_observation_missing",))
        try:
            ok = bool(predicate(after))
        except Exception as exc:  # verifier boundary must fail closed
            return VerificationResult("unknown", 0.0, (f"predicate_error:{type(exc).__name__}",))
        if ok:
            return VerificationResult("verified", 1.0, ("expected_state_observed",))
        return VerificationResult("failed", 0.0, ("expected_state_not_observed",))
