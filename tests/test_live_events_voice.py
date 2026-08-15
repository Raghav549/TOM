import pytest

from tom.live_events import LiveEventStream


@pytest.mark.asyncio
async def test_live_event_contains_voice_text_and_terminal_flag() -> None:
    stream = LiveEventStream()
    event = await stream.publish("TASK_COMPLETED", {"message": "Ho gaya bhai", "device_id": "phone-1"}, task_id="t1")
    assert event.payload["voice_text"] == "Ho gaya bhai"
    assert event.payload["terminal"] is True

    queue, replay = await stream.subscribe(task_id="t1", after=0)
    assert replay[0].seq == event.seq
    assert replay[0].payload["voice_text"] == "Ho gaya bhai"
    await stream.unsubscribe(queue)
