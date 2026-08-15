import pytest

from tom.models import Risk
from tom.planner import ModelPlanner, RulePlanner
from tom.tools import ToolRegistry


class FakeLLM:
    async def complete(self, messages, **kwargs):
        return '{"goal":"find weather","steps":[{"name":"weather.now","arguments":{"city":"Delhi"},"risk":"read"}],"explanation":"weather lookup"}'


@pytest.mark.asyncio
async def test_model_planner_validates_structured_calls() -> None:
    planner = ModelPlanner(FakeLLM(), RulePlanner())
    plan = await planner.plan(
        "find weather",
        {"available_tools": [{"name": "weather.now", "description": "current weather", "risk": "read"}]},
    )
    assert plan.steps[0].name == "weather.now"
    assert plan.steps[0].risk is Risk.READ


def test_tool_registry_discovery() -> None:
    registry = ToolRegistry({})

    class Weather:
        name = "weather.now"
        description = "current weather"
        risk = Risk.READ

        async def run(self, arguments):
            return arguments

    registry.register(Weather())
    assert registry.describe() == [{"name": "weather.now", "description": "current weather", "risk": "read"}]
