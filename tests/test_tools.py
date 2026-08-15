import pytest

from tom.models import Risk, ToolCall
from tom.tools import ToolRegistry


class FakeTool:
    name = "demo.read"
    risk = Risk.READ
    description = "test read tool"

    async def run(self, arguments):
        return {"ok": True}


def test_tool_discovery() -> None:
    registry = ToolRegistry({})
    registry.register(FakeTool())
    assert registry.describe() == [{"name": "demo.read", "description": "test read tool", "risk": "read"}]


def test_tool_risk_is_enforced() -> None:
    registry = ToolRegistry({})
    registry.register(FakeTool())
    with pytest.raises(PermissionError):
        registry.get(ToolCall(name="demo.read", risk=Risk.HIGH))
