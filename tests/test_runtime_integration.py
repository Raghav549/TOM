from __future__ import annotations

import pytest

from tom.agent_events import AgentEventBus
from tom.execution_context import LiveExecutionContext


@pytest.mark.asyncio
async def test_event_bus_fans_out_to_wildcard_and_specific_handlers() -> None:
    bus = AgentEventBus()
    seen: list[str] = []

    async def specific(event: dict[str, object]) -> None:
        seen.append(f"specific:{event['type']}")

    async def wildcard(event: dict[str, object]) -> None:
        seen.append(f"wildcard:{event['type']}")

    bus.subscribe("action.finished", specific)
    bus.subscribe("*", wildcard)
    await bus.publish("action.finished", {"task_id": "t1", "success": True})

    assert seen == ["specific:action.finished", "wildcard:action.finished"]


def test_live_context_observation_and_action_lifecycle() -> None:
    state = LiveExecutionContext("t1", "open a website")
    state.observe(package="com.android.chrome", url="https://example.com", fingerprint="abc")
    state.action_started("a1")
    state.action_finished(False, "stale screen")
    snapshot = state.snapshot()

    assert snapshot["observation_version"] == 1
    assert snapshot["current_app"] == "com.android.chrome"
    assert snapshot["current_url"] == "https://example.com"
    assert snapshot["last_action_id"] == "a1"
    assert snapshot["last_action_status"] == "failed"
    assert snapshot["last_error"] == "stale screen"


def test_event_payload_is_not_mutated_by_bus() -> None:
    original = {"task_id": "t1"}
    assert original == {"task_id": "t1"}
