from __future__ import annotations

import asyncio

from tom.perception.action_plan import GroundedActionPlan
from tom.perception.dispatch import GroundedActionDispatcher


def test_low_confidence_is_blocked() -> None:
    async def send(_: dict) -> str:
        raise AssertionError("must not dispatch")

    plan = GroundedActionPlan("tap_node", "node-1", (1, 1, 20, 20), 0.5, False, ("visual",))
    result = asyncio.run(GroundedActionDispatcher(send).dispatch(plan, task_id="t1"))
    assert result.status == "blocked"


def test_consequential_plan_requires_approval() -> None:
    async def send(_: dict) -> str:
        return "a1"

    plan = GroundedActionPlan("tap_node", "node-1", (1, 1, 20, 20), 0.95, True, ("visual", "ui_iou"))
    result = asyncio.run(GroundedActionDispatcher(send).dispatch(plan, task_id="t1"))
    assert result.status == "approval_required"


def test_grounded_plan_is_dispatched() -> None:
    messages: list[dict] = []

    async def send(message: dict) -> str:
        messages.append(message)
        return "a2"

    plan = GroundedActionPlan("tap_node", "node-1", (1, 1, 20, 20), 0.95, False, ("visual", "ui_iou"))
    result = asyncio.run(GroundedActionDispatcher(send).dispatch(plan, task_id="t2"))
    assert result.status == "sent"
    assert messages[0]["payload"]["arguments"]["node_id"] == "node-1"
