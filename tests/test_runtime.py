import pytest

from tom.approval import ApprovalGate
from tom.memory import MemoryStore
from tom.models import AgentRequest, Risk, ToolCall
from tom.planner import RulePlanner
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry


@pytest.mark.asyncio
async def test_high_risk_action_is_gated(tmp_path):
    runtime = AgentRuntime(RulePlanner(), ToolRegistry({}), MemoryStore(str(tmp_path)), ApprovalGate())
    result = await runtime.handle(AgentRequest(message="send Neha a message"))
    assert result.pending_approval
    assert result.pending_approval[0].risk == Risk.HIGH


@pytest.mark.asyncio
async def test_memory_persists_turns(tmp_path):
    runtime = AgentRuntime(RulePlanner(), ToolRegistry({}), MemoryStore(str(tmp_path)), ApprovalGate())
    request = AgentRequest(message="hello", conversation_id="c1")
    await runtime.handle(request)
    items = runtime.memory.recent("c1")
    assert [item["role"] for item in items] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_dry_run_never_executes_tools(tmp_path):
    runtime = AgentRuntime(RulePlanner(), ToolRegistry({}), MemoryStore(str(tmp_path)), ApprovalGate(required=False))
    result = await runtime.handle(AgentRequest(message="search the web for open source agents", dry_run=True))
    assert result.pending_approval
