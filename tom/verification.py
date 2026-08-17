from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from tom.action_predicates import PredicateResult, VerificationContext, default_predicates
from tom.perception import ScreenObservation


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    confidence: float
    reason: str
    observed_state: dict[str, Any] | None = None
    evidence: tuple[dict[str, Any], ...] = ()
    predicate: str | None = None


class ActionVerifier(Protocol):
    async def verify(
        self,
        before: ScreenObservation | None,
        after: ScreenObservation | None,
        expected: str,
        *,
        action: str | None = None,
        arguments: dict[str, Any] | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> VerificationResult: ...


class BasicStateVerifier:
    """Fail-closed verifier using action-specific post-state predicates.

    A changed screen is observation evidence, never success on its own.
    """

    def __init__(self) -> None:
        self.predicates = default_predicates()

    async def verify(
        self,
        before: ScreenObservation | None,
        after: ScreenObservation | None,
        expected: str,
        *,
        action: str | None = None,
        arguments: dict[str, Any] | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> VerificationResult:
        if after is None:
            return VerificationResult(False, 0.0, "no post-action observation available")

        action_name = action or expected
        context = VerificationContext(
            action=action_name,
            arguments=arguments or {},
            before=_observation_dict(before),
            after=_observation_dict(after),
            tool_result=tool_result or {},
        )
        result = self.predicates.evaluate(context)
        return _from_predicate(result, context.after, action_name)


def _from_predicate(result: PredicateResult, observed: dict[str, Any] | None, action: str) -> VerificationResult:
    return VerificationResult(
        success=result.success,
        confidence=result.confidence,
        reason=result.reason,
        observed_state=observed,
        evidence=tuple({"source": item.source, "detail": item.detail, "weight": item.weight} for item in result.evidence),
        predicate=action,
    )


def _observation_dict(observation: ScreenObservation | None) -> dict[str, Any] | None:
    if observation is None:
        return None
    if hasattr(observation, "model_dump"):
        return observation.model_dump()
    if hasattr(observation, "__dict__"):
        return dict(observation.__dict__)
    return {}
