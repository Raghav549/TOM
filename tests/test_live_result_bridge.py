import pytest

from tom.live_result_bridge import LiveResultBridge, replay_for_ui_and_voice
from tom.task_lifecycle import TaskLifecycle


@pytest.mark.asyncio
async def test_ui_and_voice_receive_same_ordered_stream() -> None:
    task = TaskLifecycle(task_id="live-1")
    bridge = LiveResultBridge(task)
    await bridge.start()
    ui = await bridge.subscribe_ui()
    voice = await bridge.subscribe_voice()

    await task.start("send message")
    await task.progress("WhatsApp khol raha hoon")
    await task.complete("Ho gaya bhai, message send ho gaya.")

    ui_events = [await ui.get(), await ui.get(), await ui.get()]
    voice_events = [await voice.get(), await voice.get(), await voice.get()]
    assert [event["sequence"] for event in ui_events] == [1, 2, 3]
    assert [event["sequence"] for event in voice_events] == [1, 2, 3]
    assert ui_events[-1]["terminal"] is True
    assert voice_events[-1]["voice_text"] == "Ho gaya bhai, message send ho gaya."
    await bridge.stop()


@pytest.mark.asyncio
async def test_reconnect_replay_includes_terminal_result() -> None:
    task = TaskLifecycle(task_id="live-2")
    await task.start("send message")
    await task.progress("Sending")
    await task.complete("Ho gaya bhai")

    replay = await replay_for_ui_and_voice(task, last_seen_sequence=1)
    assert [event["sequence"] for event in replay] == [2, 3]
    assert replay[-1]["event"] == "TASK_COMPLETED"
    assert replay[-1]["voice_text"] == "Ho gaya bhai"
