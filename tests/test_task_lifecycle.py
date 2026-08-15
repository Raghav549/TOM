import asyncio

import pytest

from tom.task_lifecycle import TaskLifecycle, TaskLifecycleRegistry


@pytest.mark.asyncio
async def test_lifecycle_order_and_terminal_result() -> None:
    task = TaskLifecycle(task_id="t1")
    await task.start("send a message")
    await task.progress("Opening WhatsApp")
    await task.action("a1", "open_app", package_name="com.whatsapp")
    await task.observation(package_name="com.whatsapp")
    await task.verification(True, reason="target screen confirmed")
    await task.complete("Message sent")

    events = await task.replay()
    assert [event.type for event in events] == [
        "TASK_STARTED", "LIVE_PROGRESS", "ACTION", "OBSERVATION", "VERIFICATION", "TASK_COMPLETED"
    ]
    assert task.terminal == "TASK_COMPLETED"
    with pytest.raises(RuntimeError):
        await task.progress("must not emit after completion")


@pytest.mark.asyncio
async def test_replay_is_gap_free_after_reconnect() -> None:
    task = TaskLifecycle(task_id="t2")
    await task.start("demo")
    await task.progress("one")
    await task.progress("two")
    await task.complete("done")

    resumed = await task.replay(last_seen_sequence=2)
    assert [event.sequence for event in resumed] == [3, 4]
    assert resumed[-1].type == "TASK_COMPLETED"


@pytest.mark.asyncio
async def test_live_subscriber_receives_terminal_event() -> None:
    task = TaskLifecycle(task_id="t3")
    queue = await task.subscribe()
    await task.start("demo")
    await task.complete("done")
    first = await queue.get()
    second = await queue.get()
    assert first.type == "TASK_STARTED"
    assert second.type == "TASK_COMPLETED"
    await task.unsubscribe(queue)


@pytest.mark.asyncio
async def test_registry_does_not_evict_active_tasks() -> None:
    registry = TaskLifecycleRegistry(max_tasks=1)
    task = await registry.create("active")
    with pytest.raises(RuntimeError, match="capacity"):
        await registry.create("second")
    await task.complete("done")
    second = await registry.create("second")
    assert second.task_id != task.task_id
