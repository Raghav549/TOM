import pytest

from tom.android_tools import AndroidDeviceTool
from tom.models import Risk


class FakeHub:
    async def request_action(self, **kwargs):
        return {
            "accepted": True,
            "status": "verified",
            "action_id": "a1",
            "verification": {
                "status": "verified",
                "predicate": "open_app.expected_package",
                "confidence": 0.99,
                "evidence": ["package"],
                "reason": "expected app is foreground",
            },
        }


@pytest.mark.asyncio
async def test_device_tool_carries_authoritative_verification() -> None:
    tool = AndroidDeviceTool("device_open_app", "open", "open_app", Risk.LOW, FakeHub())
    result = await tool.run({"device_id": "d1", "package_name": "com.whatsapp"})
    assert result["ok"] is True
    assert result["device_verification"]["status"] == "verified"
