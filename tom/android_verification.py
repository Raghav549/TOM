from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .success_predicates import SuccessPredicateEngine, VerificationState as PredicateState


class VerificationState(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VerificationEvidence:
    state: VerificationState
    reason: str
    observed: dict[str, Any] | None = None
    confidence: float = 0.0
    evidence: tuple[dict[str, Any], ...] = ()


class AndroidVerifier:
    """Device verifier backed by action-specific predicates, never ACK-only success."""

    def __init__(self) -> None:
        self._engine = SuccessPredicateEngine()

    def verify(self, expected: dict[str, Any], observation: dict[str, Any] | None) -> VerificationEvidence:
        # Compatibility: callers that pass only an expected-state mapping are
        # treated as a generic predicate. New callers should pass action+predicate.
        result = self._engine.verify({"kind": expected.get("kind", "generic"), "success_predicate": expected}, observation)
        state = VerificationState(result.state.value)
        return VerificationEvidence(
            state=state,
            reason=result.reason,
            observed=dict(result.observed),
            confidence=result.confidence,
            evidence=tuple({"kind": e.kind, "value": e.value, "confidence": e.confidence, "authoritative": e.authoritative, "source": e.source} for e in result.evidence),
        )
