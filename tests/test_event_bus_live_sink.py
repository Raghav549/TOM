import pytest

from tom.agent_events import AgentEventBus
from tom.live_events import LiveEventStream


@pytest.mark.asyncio
async def test_agent_event_bus_forwards_to_live_stream() -> None:
    stream = LiveEventStream(make_default=True)
    queue, replay = await stream.subscribe()
    assert replay == []
    await AgentEventBus().publish("action.started", {"task_id": "t1", "action_id": "a1", "tool": "device_tap"})
    event = await queue.get()
    assert event.task_id == "t1"
    assert event.type == "action.started"
    assert event.seq == 1
    assert event.payload["voice_text"]
