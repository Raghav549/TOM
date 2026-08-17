import json

import pytest

from tom.agent_events import AgentEventBus
from tom.task_persistence import DurableTaskPersistence


@pytest.mark.asyncio
async def test_event_bus_persists_task_transitions_and_predicate(tmp_path) -> None:
    persistence = DurableTaskPersistence(path=tmp_path / "tasks.jsonl")
    bus = AgentEventBus(persistence=persistence)
    await bus.publish("TASK_STARTED", {"task_id": "t1", "goal": "open app", "device_id": "d1"})
    await bus.publish("action.started", {"task_id": "t1", "action_id": "a1", "tool": "device_open_app"})
    await bus.publish("VERIFICATION", {"task_id": "t1", "action_id": "a1", "verified": True, "predicate": "package_equals", "evidence": ["com.example"]})
    await bus.publish("TASK_COMPLETED", {"task_id": "t1", "message": "done"})

    records = [json.loads(line) for line in (tmp_path / "tasks.jsonl").read_text().splitlines()]
    assert [record["event_type"] for record in records if record["kind"] == "event"] == [
        "TASK_STARTED", "action.started", "VERIFICATION", "TASK_COMPLETED"
    ]
    assert records[-1]["event_type"] == "TASK_COMPLETED"


@pytest.mark.asyncio
async def test_startup_recovery_never_replays_running_action(tmp_path) -> None:
    persistence = DurableTaskPersistence(path=tmp_path / "tasks.jsonl")
    bus = AgentEventBus(persistence=persistence)
    await bus.publish("TASK_STARTED", {"task_id": "t2", "goal": "send message", "device_id": "d1"})
    await bus.publish("action.started", {"task_id": "t2", "action_id": "a2", "tool": "device_tap"})

    restarted = DurableTaskPersistence(path=tmp_path / "tasks.jsonl")
    report = restarted.startup_recovery()
    assert report["count"] == 1
    assert report["recovered"][0]["task_id"] == "t2"
    assert report["recovered"][0]["status"] == "recovery_pending"
    assert "never replay" in report["policy"]
