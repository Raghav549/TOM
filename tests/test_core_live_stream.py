import asyncio

import pytest

from tom.live_events import LiveEventStream
from tom.api.bridge_server import AndroidBridgeHub


@pytest.mark.asyncio
async def test_live_event_stream_replays_and_filters_by_task():
    stream = LiveEventStream()
    await stream.publish("task.started", {"goal": "open settings"}, task_id="task-1")
    await stream.publish("task.progress", {"progress": 0.5}, task_id="task-2")

    queue, replay = await stream.subscribe(task_id="task-1", after=0)
    assert [item.type for item in replay] == ["task.started"]
    assert queue.empty()
    await stream.unsubscribe(queue)


@pytest.mark.asyncio
async def test_bridge_resolves_verification_waiter_for_same_task_action():
    hub = AndroidBridgeHub()
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    hub._waiters["verification:task-1:action-1"] = future

    await hub.resolve_verification({
        "task_id": "task-1",
        "action_id": "action-1",
        "verification": {"status": "verified", "confidence": 1.0},
    })

    assert (await future)["verification"]["status"] == "verified"
