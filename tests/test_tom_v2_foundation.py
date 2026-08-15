from __future__ import annotations

import pytest

from tom.action_policy import ActionPolicy, RiskLevel
from tom.api_catalog import ApiCatalog
from tom.agent_loop import AgentLoop
from tom.tool_registry import ToolRegistry, ToolSpec


@pytest.mark.parametrize("action", ["payment", "purchase", "send_message", "delete"])
def test_consequential_actions_fail_closed(action: str) -> None:
    decision = ActionPolicy().decide(action)
    assert decision.allowed is False
    assert decision.risk is RiskLevel.CONSEQUENT
    assert decision.confirmation_required is True


def test_confirmation_is_bound_and_expires() -> None:
    policy = ActionPolicy()
    token = policy.issue_confirmation("task-1", "action-1", ttl_seconds=60)
    assert policy.validate_confirmation(token, "task-1", "action-1")
    assert not policy.validate_confirmation(token, "task-2", "action-1")
    assert not policy.validate_confirmation(token, "task-1", "action-2")


def test_api_catalog_is_discovery_only() -> None:
    catalog = ApiCatalog.parse_readme(
        """
| API | Description | Auth | HTTPS | CORS |
|---|---|---|---|---|
| [Example Weather](https://example.com/weather) | Weather forecast | No | Yes | Yes |
"""
    )
    assert catalog.search("weather")[0].name == "Example Weather"


@pytest.mark.asyncio
async def test_agent_loop_observes_acts_and_verifies() -> None:
    class Observer:
        def __init__(self) -> None:
            self.calls = 0

        async def observe(self):
            self.calls += 1
            return {"screen": self.calls}

    class Planner:
        async def next_action(self, goal, state, history):
            return {"tool": "read", "arguments": {}, "done": True}

    async def handler(arguments):
        return {"value": "real"}

    tools = ToolRegistry()
    tools.register(ToolSpec("read", "real read tool", handler, risk_action="read"))
    observer = Observer()
    result = await AgentLoop(Planner(), observer, tools).run("check the screen")

    assert result["status"] == "completed"
    assert observer.calls == 2
    assert result["history"][0]["result"]["ok"] is True
