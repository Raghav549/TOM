from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Surface(str, Enum):
    BROWSER = "browser"
    ANDROID = "android"
    IOS = "ios"
    DESKTOP = "desktop"


@dataclass(frozen=True)
class ScreenState:
    surface: Surface
    title: str = ""
    url: str | None = None
    screenshot_ref: str | None = None
    visible_text: str = ""


class DeviceAdapter(Protocol):
    async def observe(self) -> ScreenState: ...
    async def click(self, x: float, y: float) -> None: ...
    async def type_text(self, text: str) -> None: ...
    async def press(self, key: str) -> None: ...
    async def scroll(self, delta: float) -> None: ...


class BrowserAdapter(DeviceAdapter, Protocol):
    async def navigate(self, url: str) -> None: ...
    async def go_back(self) -> None: ...
