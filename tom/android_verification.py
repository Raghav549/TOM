from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class VerificationState(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VerificationEvidence:
    state: VerificationState
    reason: str
    observed: dict[str, Any] | None = None


class AndroidVerifier:
    """Conservative verification: transport ACK is never treated as task success."""

    def verify(self, expected: dict[str, Any], observation: dict[str, Any] | None) -> VerificationEvidence:
        if observation is None:
            return VerificationEvidence(VerificationState.UNKNOWN, "no post-action observation")
        for key, expected_value in expected.items():
            if observation.get(key) != expected_value:
                return VerificationEvidence(
                    VerificationState.FAILED,
                    f"expected {key}={expected_value!r}, observed {observation.get(key)!r}",
                    observation,
                )
        return VerificationEvidence(VerificationState.VERIFIED, "expected state observed", observation)
