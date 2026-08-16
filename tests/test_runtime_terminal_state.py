import pytest

from tom.approval import ApprovalGate
from tom.agent_events import AgentEventBus
from tom.memory import MemoryStore
from tom.models import AgentRequest, Plan, ToolCall, Risk
from tom.permissions import PermissionPolicy
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry


class ApprovalPlanner:
    async def plan(self, message, context):
        return Plan(
            goal=message,
            steps=[ToolCall(name="communication.sms_send", arguments={"to": "+10000000000", "body": "hello"}, risk=Risk.HIGH)],
        )


class Reply:
    async def respond(self, **kwargs):
        return "Waiting for your approval."

    async def stream(self, **kwargs):
        yield "Waiting for your approval."


@pytest.mark.asyncio
async def test_pending_approval_is_not_task_completed(tmp_path):
    bus = AgentEventBus()
    seen = []

    async def collect(event):
        seen.append(event)

    bus.subscribe("*", collect)
    runtime = AgentRuntime(
        ApprovalPlanner(),
        ToolRegistry({}),
        MemoryStore(str(tmp_path)),
        ApprovalGate(True),
        PermissionPolicy(),
        Reply(),
        events_bus=bus,
    )
    result = await runtime.handle(AgentRequest(message="send sms", conversation_id="c1"))
    assert result.pending_approval
    assert not any(event["type"] == "TASK_COMPLETED" for event in seen)
    assert any(event["type"] == "task.waiting_approval" for event in seen)
