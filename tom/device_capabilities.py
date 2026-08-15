from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum


class CapabilityState(str, Enum):
    AVAILABLE = "available"
    REQUIRES_USER_GRANT = "requires_user_grant"
    REQUIRES_DEVICE_SETUP = "requires_device_setup"
    UNSUPPORTED = "unsupported_on_device"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    BLOCKED = "blocked_by_policy"


@dataclass(frozen=True)
class DeviceCapability:
    id: str
    state: CapabilityState
    methods: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass
class DeviceCapabilityRegistry:
    """Single source of truth for what the connected device can really do."""

    capabilities: dict[str, DeviceCapability] = field(default_factory=dict)

    def register(self, capability: DeviceCapability) -> None:
        self.capabilities[capability.id] = capability

    def get(self, capability_id: str) -> DeviceCapability | None:
        return self.capabilities.get(capability_id)

    def available(self, capability_id: str) -> bool:
        capability = self.get(capability_id)
        return capability is not None and capability.state is CapabilityState.AVAILABLE

    def describe(self) -> list[dict[str, object]]:
        return [
            {
                "id": item.id,
                "state": item.state.value,
                "methods": list(item.methods),
                "limitations": list(item.limitations),
            }
            for item in self.capabilities.values()
        ]

    def require(self, capability_id: str) -> DeviceCapability:
        capability = self.get(capability_id)
        if capability is None:
            raise LookupError(f"unknown device capability: {capability_id}")
        if capability.state is not CapabilityState.AVAILABLE:
            raise PermissionError(
                f"device capability '{capability_id}' is {capability.state.value}"
            )
        return capability

    @classmethod
    def android_baseline(cls, granted: Iterable[str] = ()) -> DeviceCapabilityRegistry:
        granted_set = set(granted)
        registry = cls()
        definitions = {
            "android.accessibility.ui_tree": ("observe_window", "find_node", "read_visible_text"),
            "android.accessibility.actions": ("click", "set_text", "scroll", "global_back", "global_home", "global_recents"),
            "android.accessibility.gestures": ("tap", "swipe", "multi_touch"),
            "android.accessibility.screenshot": ("capture_screen",),
            "android.notifications": ("observe_posted", "observe_removed", "list_active"),
            "android.media_projection": ("capture_display",),
            "android.adb.dev_bridge": ("shell", "install", "diagnostics"),
        }
        grant_map = {
            "android.accessibility.ui_tree": "accessibility",
            "android.accessibility.actions": "accessibility",
            "android.accessibility.gestures": "accessibility",
            "android.accessibility.screenshot": "accessibility_screenshot",
            "android.notifications": "notifications",
            "android.media_projection": "media_projection",
            "android.adb.dev_bridge": "adb",
        }
        for capability_id, methods in definitions.items():
            grant = grant_map[capability_id]
            state = CapabilityState.AVAILABLE if grant in granted_set else CapabilityState.REQUIRES_USER_GRANT
            if grant == "adb" and grant not in granted_set:
                state = CapabilityState.REQUIRES_DEVICE_SETUP
            registry.register(DeviceCapability(capability_id, state, methods))
        return registry
