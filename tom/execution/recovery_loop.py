from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from tom.perception.action_verifier import ActionVerifier, VerificationResult
from tom.perception.multimodal_observation import MultimodalObservation


class RecoveryDecision(str, Enum):
    VERIFIED = "verified"
    REGROUND = "re-ground"
    ASK_USER = "ask_user"
    ABORT = "abort"


@dataclass(frozen=True)
class RecoveryPolicy:
    max_retries: int = 1
    max_total_attempts: int = 2


@dataclass(frozen=True)
class RecoveryOutcome:
    decision: RecoveryDecision
    attempts: int
    verification: VerificationResult
    reason: str


class PostActionRecoveryLoop:
    """Closed-loop action verification. It fails closed and never blind-retries."""

    def __init__(self, verifier: ActionVerifier | None = None, policy: RecoveryPolicy | None = None) -> None:
        self.verifier = verifier or ActionVerifier()
        self.policy = policy or RecoveryPolicy()

    async def run(
        self,
        before: MultimodalObservation,
        execute: Callable[[int], Awaitable[None]],
        observe_after: Callable[[int], Awaitable[MultimodalObservation | None]],
        expected_state: Callable[[MultimodalObservation], bool],
        re_ground: Callable[[int, MultimodalObservation], Awaitable[bool]],
        request_user: Callable[[str], Awaitable[None]],
    ) -> RecoveryOutcome:
        attempts = 0
        current_before = before
        last = VerificationResult("unknown", 0.0, ("not_attempted",))

        while attempts < self.policy.max_total_attempts:
            attempts += 1
            await execute(attempts)
            after = await observe_after(attempts)
            last = self.verifier.verify(current_before, after, expected_state)

            if last.status == "verified":
                return RecoveryOutcome(RecoveryDecision.VERIFIED, attempts, last, "expected state verified")

            if after is None:
                await request_user("I couldn't verify the result on screen, so I stopped instead of repeating the action.")
                return RecoveryOutcome(RecoveryDecision.ASK_USER, attempts, last, "post-action observation unavailable")

            if attempts > self.policy.max_retries:
                await request_user("The action did not reach the expected screen state. What should I do next?")
                return RecoveryOutcome(RecoveryDecision.ASK_USER, attempts, last, "retry budget exhausted")

            grounded = await re_ground(attempts, after)
            if not grounded:
                await request_user("The screen changed and I couldn't safely re-locate the target.")
                return RecoveryOutcome(RecoveryDecision.ASK_USER, attempts, last, "re-grounding failed")

            current_before = after

        return RecoveryOutcome(RecoveryDecision.ABORT, attempts, last, "safety budget exhausted")
