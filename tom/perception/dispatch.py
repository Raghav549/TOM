from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .action_plan import GroundedActionPlan
from .execution_gate import GroundedExecutionGate


@dataclass(frozen=True)
class DispatchResult:
    status: str
    action_id: str | None = None
    reason: str = ""


class GroundedActionDispatcher:
    """Dispatches only already-grounded tap plans to an authenticated bridge.

    The bridge remains the final device-side policy gate and must require its
    own task/approval context for consequential operations.
    """

    def __init__(self, send_action: Callable[[dict], Awaitable[str]]) -> None:
        self.send_action = send_action
        self.gate = GroundedExecutionGate()

    async def dispatch(self, plan: GroundedActionPlan, *, task_id: str, approval_token: str | None = None) -> DispatchResult:
        decision = self.gate.evaluate(plan, approved=bool(approval_token))
        if not decision.executable:
            return DispatchResult(
                status="approval_required" if decision.requires_approval else "blocked",
                reason=decision.reason,
            )
        action_id = await self.send_action({
            "type": "action_request",
            "payload": {
                "task_id": task_id,
                "action_id": f"tap:{task_id}:{plan.node_id}",
                "action": plan.action,
                "arguments": {"node_id": plan.node_id},
                "approval_token": approval_token or "",
                "expected": {"node_id": plan.node_id, "bounds": list(plan.bounds)},
            },
        })
        return DispatchResult(status="sent", action_id=action_id, reason=decision.reason)
