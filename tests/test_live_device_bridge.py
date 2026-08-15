import asyncio

import pytest

from tom.device.live import DeviceSession, LiveDeviceRegistry, RemoteDeviceTool
from tom.models import Risk, ToolCall


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)

    async def close(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_remote_tool_waits_for_real_android_result():
    registry = LiveDeviceRegistry()
    socket = FakeWebSocket()
    session = DeviceSession("phone-1", socket, authenticated=True)
    registry.sessions["phone-1"] = session
    tool = RemoteDeviceTool("device_back", Risk.LOW, registry)

    task = asyncio.create_task(tool.run({"device_id": "phone-1", "task_id": "task-1"}))
    await asyncio.sleep(0)
    assert socket.messages[0]["type"] == "action_request"
    action_id = socket.messages[0]["payload"]["action_id"]

    future = session.pending[action_id]
    future.set_result({"action_id": action_id, "accepted": True, "status": "completed"})
    result = await task
    assert result["status"] == "completed"


def test_register_tools_exposes_real_device_capabilities():
    registry = LiveDeviceRegistry()
    class Tools:
        def __init__(self):
            self.tools = {}
        def register(self, tool):
            self.tools[tool.name] = tool
    tools = Tools()
    registry.register_tools(tools)
    assert "device_search_google" in tools.tools
    assert tools.tools["device_upi_payment"].risk is Risk.CRITICAL
