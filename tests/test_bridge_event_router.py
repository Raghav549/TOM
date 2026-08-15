import pytest

from tom.bridge.runtime_event_router import AndroidBridgeEventRouter, BridgeEvent
from tom.execution.android_recovery_runtime import (
    AndroidActionRecoveryRuntime,
    AndroidExecutionState,
)
from tom.perception.action_plan import GroundedActionPlan
from tom.perception.multimodal_observation import MultimodalObservation


def plan(node="send"):
    return GroundedActionPlan("tap_node", node, (0, 0, 100, 100), 0.95, False, ("visual", "ui_iou"))


def obs(name):
    return MultimodalObservation.now(name, "com.example")


@pytest.mark.asyncio
async def test_action_ack_observation_verification_flow():
    runtime = AndroidActionRecoveryRuntime()
    router = AndroidBridgeEventRouter(runtime)
    sent = []

    async def send(event):
        sent.append(event)
        if event.type == "action_request":
            await router.on_event(BridgeEvent("action_ack", event.correlation_id, {"accepted": True}, event.seq + 1))
        elif event.type == "observation_request":
            await router.on_event(BridgeEvent("observation", event.correlation_id, {"observation": obs("after")}, event.seq + 1))

    async def reground(after, old): return old
    async def ask(msg): pass

    result = await router.execute(plan(), obs("before"), send, lambda o: o.observation_id == "after", reground, ask, "task-1")
    assert result.state is AndroidExecutionState.VERIFIED
    assert [e.type for e in sent] == ["action_request", "observation_request"]


@pytest.mark.asyncio
async def test_missing_observation_does_not_retry():
    runtime = AndroidActionRecoveryRuntime()
    router = AndroidBridgeEventRouter(runtime)
    sent = []

    async def send(event):
        sent.append(event)
        if event.type == "action_request":
            await router.on_event(BridgeEvent("action_ack", event.correlation_id, {"accepted": True}, event.seq + 1))

    async def reground(after, old): return old
    async def ask(msg): pass

    result = await router.execute(plan(), obs("before"), send, lambda _: True, reground, ask, "task-2")
    assert result.state is AndroidExecutionState.NEEDS_USER
    assert [e.type for e in sent] == ["action_request", "observation_request"]


@pytest.mark.asyncio
async def test_mismatch_regrounds_then_sends_new_action():
    runtime = AndroidActionRecoveryRuntime()
    router = AndroidBridgeEventRouter(runtime)
    sent = []
    count = 0

    async def send(event):
        nonlocal count
        sent.append(event)
        if event.type == "action_request":
            await router.on_event(BridgeEvent("action_ack", event.correlation_id, {"accepted": True}, event.seq + 1))
        else:
            count += 1
            await router.on_event(BridgeEvent("observation", event.correlation_id, {"observation": obs(f"after-{count}")}, event.seq + 1))

    async def reground(after, old): return plan("new-target")
    async def ask(msg): pass

    result = await router.execute(plan(), obs("before"), send,
        lambda o: o.observation_id == "after-2", reground, ask, "task-3")
    assert result.state is AndroidExecutionState.VERIFIED
    assert [e.type for e in sent] == ["action_request", "observation_request", "action_request", "observation_request"]
    assert sent[2].payload["node_id"] == "new-target"
