from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from tom.perception import ScreenObservation


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    confidence: float
    reason: str
    observed_state: dict[str, Any] | None = None


class ActionVerifier(Protocol):
    async def verify(
        self,
        before: ScreenObservation | None,
        after: ScreenObservation | None,
        expected: str,
    ) -> VerificationResult: ...


class BasicStateVerifier:
    """Conservative verifier: never treats an absent observation as success."""

    async def verify(
        self,
        before: ScreenObservation | None,
        after: ScreenObservation | None,
        expected: str,
    ) -> VerificationResult:
        if after is None:
            return VerificationResult(False, 0.0, "no post-action observation available")
        if before is not None and after == before:
            return VerificationResult(False, 0.15, "post-action state did not change")
        return VerificationResult(
            True,
            0.55,
            f"post-action observation received; semantic verification still required for: {expected}",
        )
