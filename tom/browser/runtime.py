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
    """Real visible browser runtime with grounded interaction primitives."""

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

    async def click_role(self, role: str, name: str, exact: bool = False) -> BrowserSnapshot:
        page = self._require_page()
        await page.get_by_role(role, name=name, exact=exact).first.click()
        return await self.snapshot()

    async def fill(self, selector: str, value: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.fill(value)
        return await self.snapshot()

    async def fill_label(self, label: str, value: str, exact: bool = False) -> BrowserSnapshot:
        page = self._require_page()
        await page.get_by_label(label, exact=exact).first.fill(value)
        return await self.snapshot()

    async def press(self, selector: str, key: str = "Enter") -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.press(key)
        return await self.snapshot()

    async def press_key(self, key: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.keyboard.press(key)
        return await self.snapshot()

    async def scroll(self, *, amount: int = 700, selector: str | None = None) -> BrowserSnapshot:
        page = self._require_page()
        if selector:
            await page.locator(selector).first.scroll_into_view_if_needed()
        else:
            await page.mouse.wheel(0, amount)
        return await self.snapshot()

    async def check(self, selector: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.check()
        return await self.snapshot()

    async def uncheck(self, selector: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.uncheck()
        return await self.snapshot()

    async def select(self, selector: str, value: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.select_option(value)
        return await self.snapshot()

    async def hover(self, selector: str) -> BrowserSnapshot:
        page = self._require_page()
        await page.locator(selector).first.hover()
        return await self.snapshot()

    async def wait_for(self, selector: str | None = None, timeout_ms: int = 1000) -> BrowserSnapshot:
        page = self._require_page()
        timeout_ms = max(0, min(30_000, int(timeout_ms)))
        if selector:
            await page.locator(selector).first.wait_for(timeout=timeout_ms)
        else:
            await page.wait_for_timeout(timeout_ms)
        return await self.snapshot()

    async def reload(self) -> BrowserSnapshot:
        page = self._require_page()
        await page.reload(wait_until="domcontentloaded")
        return await self.snapshot()

    async def back(self) -> BrowserSnapshot:
        page = self._require_page()
        await page.go_back(wait_until="domcontentloaded")
        return await self.snapshot()
