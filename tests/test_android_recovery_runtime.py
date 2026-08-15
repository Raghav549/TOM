import pytest

from tom.execution.android_recovery_runtime import (
    AndroidActionRecoveryRuntime,
    AndroidExecutionState,
)
from tom.execution.recovery_loop import RecoveryPolicy
from tom.perception.action_plan import GroundedActionPlan
from tom.perception.multimodal_observation import MultimodalObservation


def plan(node="send"):
    return GroundedActionPlan("tap_node", node, (0, 0, 100, 100), 0.9, False, ("visual", "ui_iou"))


def observation(i):
    return MultimodalObservation.now(i, "com.example")


@pytest.mark.asyncio
async def test_tap_verify_success():
    runtime = AndroidActionRecoveryRuntime()
    events = []

    async def dispatch(p, attempt): events.append(("dispatch", p.node_id, attempt))
    async def observe(attempt): return observation(f"after-{attempt}")
    async def reground(after, old): return old
    async def ask(msg): events.append(("ask", msg))

    result = await runtime.execute(plan(), observation("before"), dispatch, observe, lambda _: True, reground, ask)
    assert result.state is AndroidExecutionState.VERIFIED
    assert events[0] == ("dispatch", "send", 1)


@pytest.mark.asyncio
async def test_mismatch_regrounds_before_retry():
    runtime = AndroidActionRecoveryRuntime(policy=RecoveryPolicy(max_retries=1, max_total_attempts=2))
    events = []

    async def dispatch(p, attempt): events.append((p.node_id, attempt))
    async def observe(attempt): return observation(f"after-{attempt}")
    async def reground(after, old): return plan("new-target")
    async def ask(msg): pass

    result = await runtime.execute(plan(), observation("before"), dispatch, observe,
        lambda o: o.observation_id == "after-2", reground, ask)
    assert result.state is AndroidExecutionState.VERIFIED
    assert events == [("send", 1), ("new-target", 2)]


@pytest.mark.asyncio
async def test_missing_observation_stops_without_retry():
    runtime = AndroidActionRecoveryRuntime()
    attempts = []

    async def dispatch(p, attempt): attempts.append(attempt)
    async def observe(attempt): return None
    async def reground(after, old): return old
    async def ask(msg): pass

    result = await runtime.execute(plan(), observation("before"), dispatch, observe, lambda _: True, reground, ask)
    assert result.state is AndroidExecutionState.NEEDS_USER
    assert attempts == [1]
