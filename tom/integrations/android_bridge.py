from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ScreenState


@dataclass
class AndroidBridge:
    """Transport-neutral Android bridge.

    A real Android client must implement this contract using AccessibilityService,
    notification listeners and explicit user-granted permissions. This server-side
    class deliberately does not pretend those capabilities exist by itself.
    """

    transport: Any

    async def observe(self) -> ScreenState:
        payload = await self.transport.request("screen.observe")
        return ScreenState(**payload)

    async def click(self, x: int, y: int) -> dict[str, Any]:
        return await self.transport.request("screen.click", {"x": x, "y": y})

    async def type_text(self, text: str) -> dict[str, Any]:
        return await self.transport.request("screen.type", {"text": text})

    async def scroll(self, delta: int) -> dict[str, Any]:
        return await self.transport.request("screen.scroll", {"delta": delta})

    async def press_back(self) -> dict[str, Any]:
        return await self.transport.request("screen.back")

    async def notification_subscribe(self) -> Any:
        return await self.transport.request("notifications.subscribe")
