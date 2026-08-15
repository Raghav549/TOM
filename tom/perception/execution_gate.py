from __future__ import annotations

from dataclasses import dataclass

from .action_plan import GroundedActionPlan

CONSEQUENTIAL_INTENTS = {
    "send_message", "send_email", "purchase", "payment", "delete",
    "account_change", "share_sensitive_data", "publish", "post",
}


@dataclass(frozen=True)
class ExecutionDecision:
    executable: bool
    requires_approval: bool
    reason: str


class GroundedExecutionGate:
    """Final gate between perception/planning and a device action.

    It never executes anything. It only decides whether a plan is eligible to
    be dispatched to the already-authenticated Android bridge.
    """

    def evaluate(self, plan: GroundedActionPlan, *, approved: bool = False) -> ExecutionDecision:
        if plan.action != "tap_node":
            return ExecutionDecision(False, False, "unsupported_action")
        if not plan.node_id or not plan.bounds:
            return ExecutionDecision(False, False, "target_not_grounded")
        if plan.confidence < 0.72:
            return ExecutionDecision(False, False, "confidence_below_threshold")
        if plan.requires_approval and not approved:
            return ExecutionDecision(False, True, "approval_required")
        return ExecutionDecision(True, False, "grounded_and_authorized")
