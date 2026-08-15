from __future__ import annotations

import pytest

from tom.agent_events import AgentEventBus
from tom.execution_context import LiveExecutionContext
from tom.live_loop import LiveDeviceLoop


class DummyPlanner:
    def __init__(self) -> None:
        self.calls = []

    async def plan(self, goal, context):
        self.calls.append((goal, context))
        return type("Plan", (), {
            "goal": goal,
            "steps": [],
            "model_dump": lambda self: {"goal": self.goal, "steps": []},
        })()


@pytest.mark.asyncio
async def test_observation_updates_live_context_and_replans() -> None:
    planner = DummyPlanner()
    bus = AgentEventBus()
    events = []

    async def collect(event):
        events.append(event)

    bus.subscribe("*", collect)
    loop = LiveDeviceLoop(planner, bus, LiveExecutionContext("task-1", "find a flight"))

    await loop.start("find a flight", memory=[], tools=[])
    await loop.observation(
        package="com.android.chrome",
        url="https://www.google.com/travel/flights",
        fingerprint="screen-1",
        source="android_accessibility+screenshot",
        action_id="a1",
    )
    await loop.replan(goal="find a flight", memory=[], tools=[])

    assert loop.context.snapshot()["current_app"] == "com.android.chrome"
    assert loop.context.snapshot()["current_url"] == "https://www.google.com/travel/flights"
    assert [event["type"] for event in events] == [
        "task.started", "plan.created", "observation.received", "screen.changed", "plan.replanned"
    ]
    assert len(planner.calls) == 2


@pytest.mark.asyncio
async def test_failed_action_emits_recovery_signal() -> None:
    planner = DummyPlanner()
    bus = AgentEventBus()
    events = []

    async def collect(event):
        events.append(event)

    bus.subscribe("*", collect)
    loop = LiveDeviceLoop(planner, bus, LiveExecutionContext("task-2", "open settings"))
    await loop.start("open settings", memory=[], tools=[])
    await loop.action_result(action_id="a1", success=False, error="stale screen")

    assert events[-1]["type"] == "action.failed"
    assert events[-1]["error"] == "stale screen"
