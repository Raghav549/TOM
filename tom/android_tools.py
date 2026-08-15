from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4
from urllib.parse import quote_plus

from .api.bridge_server import AndroidBridgeHub
from .models import Risk
from .tools import ToolRegistry


@dataclass
class AndroidDeviceTool:
    name: str
    description: str
    action: str
    risk: Risk
    hub: AndroidBridgeHub

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        device_id = str(arguments.get("device_id", "")).strip()
        if not device_id:
            raise ValueError("device_id is required")
        task_id = str(arguments.get("task_id") or uuid4())
        approval = arguments.get("approval_token")
        action_arguments = {key: value for key, value in arguments.items() if key not in {"device_id", "task_id", "approval_token"}}

        result = await self.hub.request_action(
            device_id=device_id,
            task_id=task_id,
            action=self.action,
            arguments=action_arguments,
            approval_token=str(approval) if approval else None,
        )
        if not result.get("accepted") or result.get("status") != "completed":
            return {"ok": False, "action": self.action, "result": result}

        observation = await self.hub.request_observation(device_id, task_id, str(result.get("action_id")), timeout=8.0)
        if observation is None:
            return {"ok": False, "action": self.action, "result": result, "verification": None, "error": "post_action_observation_timeout"}
        return {"ok": True, "action": self.action, "result": result, "verification": observation}


def register_android_tools(registry: ToolRegistry, hub: AndroidBridgeHub) -> None:
    specs = [
        ("device_open_app", "Open a real Android app by package name.", "open_app", Risk.LOW),
        ("device_open_url", "Open a real website URL in the device browser.", "open_url", Risk.LOW),
        ("device_search_google", "Open Google search with a user query.", "search_google", Risk.LOW),
        ("device_tap", "Tap a grounded screen coordinate.", "tap", Risk.LOW),
        ("device_tap_node", "Click a grounded accessibility node.", "tap_node", Risk.LOW),
        ("device_type", "Type into a grounded editable accessibility node.", "set_text_node", Risk.LOW),
        ("device_swipe", "Swipe between grounded screen coordinates.", "swipe", Risk.LOW),
        ("device_long_press", "Long-press a grounded screen coordinate.", "long_press", Risk.LOW),
        ("device_long_click_node", "Long-click a grounded accessibility node.", "long_click_node", Risk.LOW),
        ("device_select_node", "Select a grounded accessibility node.", "select_node", Risk.LOW),
        ("device_scroll_forward", "Scroll a grounded scrollable node forward.", "scroll_node_forward", Risk.LOW),
        ("device_scroll_backward", "Scroll a grounded scrollable node backward.", "scroll_node_backward", Risk.LOW),
        ("device_back", "Navigate back on Android.", "back", Risk.LOW),
        ("device_home", "Go to Android home.", "home", Risk.LOW),
        ("device_recents", "Open Android recent apps.", "recents", Risk.LOW),
        ("device_maps_search", "Open a real map search on the device.", "open_url", Risk.LOW),
        ("device_upi_payment", "Open a UPI payment request. Requires exact user confirmation and provider-side verification.", "open_intent_uri", Risk.CRITICAL),
        ("device_compose_email", "Open a real email composer with the supplied recipient/content.", "compose_email", Risk.HIGH),
        ("device_compose_sms", "Open a real SMS composer with the supplied number/content.", "compose_sms", Risk.HIGH),
    ]
    for name, description, action, risk in specs:
        registry.register(AndroidDeviceTool(name, description, action, risk, hub))


async def prepare_android_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Normalize high-level convenience arguments into bridge-native arguments."""
    result = dict(arguments)
    if tool_name == "device_search_google" and result.get("query"):
        result["url"] = f"https://www.google.com/search?q={quote_plus(str(result.pop('query')))}"
    elif tool_name == "device_maps_search" and result.get("query"):
        result["url"] = f"https://www.google.com/maps/search/?api=1&query={quote_plus(str(result.pop('query')))}"
    return result
