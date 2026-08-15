from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .safety import BrowserSafetyPolicy, NavigationDecision


@dataclass(frozen=True)
class BrowserSnapshot:
    url: str
    title: str
    text: str


class BrowserSession:
    """Small Playwright boundary with safety checks kept outside the planner."""

    def __init__(self, page: Any, *, safety: BrowserSafetyPolicy | None = None) -> None:
        self.page = page
        self.safety = safety or BrowserSafetyPolicy()

    async def navigate(self, url: str) -> NavigationDecision:
        decision = self.safety.check_navigation(url)
        if not decision.allowed:
            return decision
        await self.page.goto(url, wait_until="domcontentloaded")
        return decision

    async def snapshot(self, *, max_text_chars: int = 20_000) -> BrowserSnapshot:
        if max_text_chars < 1:
            raise ValueError("max_text_chars must be positive")
        text = await self.page.locator("body").inner_text()
        return BrowserSnapshot(
            url=str(self.page.url),
            title=str(await self.page.title()),
            text=text[:max_text_chars],
        )

    async def click(self, selector: str) -> None:
        if not selector.strip():
            raise ValueError("selector must not be empty")
        await self.page.locator(selector).click()
