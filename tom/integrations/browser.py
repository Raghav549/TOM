from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ScreenState


@dataclass
class PlaywrightBrowser:
    """Browser adapter for a user-owned browser context.

    The host application is responsible for attaching an authenticated context.
    TOM does not collect passwords or bypass authentication controls.
    """

    page: Any

    async def open(self, url: str) -> dict[str, Any]:
        await self.page.goto(url, wait_until="domcontentloaded")
        return {"url": self.page.url, "title": await self.page.title()}

    async def navigate(self, url: str) -> dict[str, Any]:
        return await self.open(url)

    async def observe(self) -> ScreenState:
        elements = await self.page.locator("button, input, textarea, a, select").evaluate_all(
            "els => els.slice(0, 200).map((e,i) => ({i, tag:e.tagName, text:(e.innerText||e.value||'').slice(0,300), aria:e.getAttribute('aria-label')}))"
        )
        viewport = await self.page.evaluate("() => ({width: innerWidth, height: innerHeight})")
        return ScreenState(source="browser", width=viewport["width"], height=viewport["height"], elements=elements)

    async def click(self, x: int, y: int) -> dict[str, Any]:
        await self.page.mouse.click(x, y)
        return {"clicked": True, "x": x, "y": y}

    async def type_text(self, text: str) -> dict[str, Any]:
        await self.page.keyboard.insert_text(text)
        return {"typed": True, "length": len(text)}
