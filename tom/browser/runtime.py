from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .safety import BrowserSafetyPolicy


@dataclass(frozen=True)
class BrowserSnapshot:
    url: str
    title: str
    text: str


class PlaywrightBrowser:
    """Real visible browser runtime with an explicit navigation safety boundary."""

    def __init__(self, *, allowed_hosts: set[str] | None = None, headless: bool = False) -> None:
        self.policy = BrowserSafetyPolicy(allowed_hosts=allowed_hosts)
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def ensure_started(self) -> None:
        if self._page is None:
            await self.start()

    async def start(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Install TOM browser support with the browser extra") from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None

    def _require_page(self) -> Any:
        if self._page is None:
            raise RuntimeError("browser session is not started")
        return self._page

    async def goto(self, url: str) -> BrowserSnapshot:
        decision = self.policy.check_navigation(url)
        if not decision.allowed:
            raise PermissionError(f"browser navigation blocked: {decision.reason}")
        page = self._require_page()
        await page.goto(url, wait_until="domcontentloaded")
        return await self.snapshot()

    async def snapshot(self, max_text: int = 20_000) -> BrowserSnapshot:
        page = self._require_page()
        text = await page.locator("body").inner_text(timeout=5_000)
        return BrowserSnapshot(page.url, await page.title(), text[:max_text])

    async def click(self, selector: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.click()
        return await self.snapshot()

    async def fill(self, selector: str, value: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.fill(value)
        return await self.snapshot()

    async def back(self) -> BrowserSnapshot:
        page = self._require_page()
        await page.go_back(wait_until="domcontentloaded")
        return await self.snapshot()
