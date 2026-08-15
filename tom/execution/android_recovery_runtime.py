from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from tom.execution.recovery_loop import RecoveryPolicy
from tom.perception.action_plan import GroundedActionPlan
from tom.perception.action_verifier import ActionVerifier, VerificationResult
from tom.perception.multimodal_observation import MultimodalObservation


class AndroidExecutionState(str, Enum):
    READY = "ready"
    DISPATCHING = "dispatching"
    WAITING_OBSERVATION = "waiting_observation"
    VERIFYING = "verifying"
    REGROUNDING = "regrounding"
    RETRYING = "retrying"
    VERIFIED = "verified"
    NEEDS_USER = "needs_user"
    ABORTED = "aborted"


@dataclass(frozen=True)
class AndroidExecutionResult:
    state: AndroidExecutionState
    attempts: int
    verification: VerificationResult
    reason: str


class AndroidActionRecoveryRuntime:
    """Runtime state machine for a grounded Android action.

    The Android bridge is supplied as callbacks so transport/auth stay independent.
    A transport ACK is only an execution receipt; success requires a fresh
    observation and explicit expected-state verification.
    """

    def __init__(self, verifier: ActionVerifier | None = None, policy: RecoveryPolicy | None = None) -> None:
        self.verifier = verifier or ActionVerifier()
        self.policy = policy or RecoveryPolicy()
        self.state = AndroidExecutionState.READY

    async def execute(
        self,
        plan: GroundedActionPlan,
        before: MultimodalObservation,
        dispatch: Callable[[GroundedActionPlan, int], Awaitable[None]],
        observe: Callable[[int], Awaitable[MultimodalObservation | None]],
        verify_expected: Callable[[MultimodalObservation], bool],
        reground: Callable[[MultimodalObservation, GroundedActionPlan], Awaitable[GroundedActionPlan | None]],
        ask_user: Callable[[str], Awaitable[None]],
    ) -> AndroidExecutionResult:
        current_before = before
        current_plan = plan
        last = VerificationResult("unknown", 0.0, ("not_attempted",))

        for attempt in range(1, self.policy.max_total_attempts + 1):
            self.state = AndroidExecutionState.DISPATCHING
            await dispatch(current_plan, attempt)

            self.state = AndroidExecutionState.WAITING_OBSERVATION
            after = await observe(attempt)
            if after is None:
                self.state = AndroidExecutionState.NEEDS_USER
                last = VerificationResult("unknown", 0.0, ("post_action_observation_missing",))
                await ask_user("Bhai, action ka screen result verify nahi ho paaya, isliye maine repeat nahi kiya.")
                return AndroidExecutionResult(self.state, attempt, last, "observation unavailable")

            self.state = AndroidExecutionState.VERIFYING
            last = self.verifier.verify(current_before, after, verify_expected)
            if last.status == "verified":
                self.state = AndroidExecutionState.VERIFIED
                return AndroidExecutionResult(self.state, attempt, last, "expected state verified")

            if attempt >= self.policy.max_total_attempts:
                self.state = AndroidExecutionState.NEEDS_USER
                await ask_user("Bhai, expected state nahi mila. Main aur action repeat nahi karunga bina tumhare bolne ke.")
                return AndroidExecutionResult(self.state, attempt, last, "retry budget exhausted")

            self.state = AndroidExecutionState.REGROUNDING
            new_plan = await reground(after, current_plan)
            if new_plan is None:
                self.state = AndroidExecutionState.NEEDS_USER
                await ask_user("Screen change ho gayi aur target safely re-locate nahi hua. Kya karun?")
                return AndroidExecutionResult(self.state, attempt, last, "re-grounding failed")

            current_before = after
            current_plan = new_plan
            self.state = AndroidExecutionState.RETRYING

        self.state = AndroidExecutionState.ABORTED
        return AndroidExecutionResult(self.state, self.policy.max_total_attempts, last, "safety budget exhausted")
