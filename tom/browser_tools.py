from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .browser.runtime import PlaywrightBrowser
from .models import Risk
from .tools import ToolRegistry


@dataclass
class BrowserRuntimeTool:
    name: str
    description: str
    risk: Risk
    runtime: PlaywrightBrowser

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.runtime.ensure_started()
        page = self.runtime._require_page()
        if self.name == "browser_open":
            return (await self.runtime.goto(str(arguments["url"]))).__dict__
        if self.name == "browser_snapshot":
            return (await self.runtime.snapshot()).__dict__
        if self.name == "browser_click":
            return (await self.runtime.click(str(arguments["selector"]))).__dict__
        if self.name == "browser_click_text":
            await page.get_by_text(str(arguments["text"]), exact=bool(arguments.get("exact", False))).first.click()
            return (await self.runtime.snapshot()).__dict__
        if self.name == "browser_fill":
            return (await self.runtime.fill(str(arguments["selector"]), str(arguments["value"]))).__dict__
        if self.name == "browser_fill_label":
            await page.get_by_label(str(arguments["label"]), exact=bool(arguments.get("exact", False))).first.fill(str(arguments["value"]))
            return (await self.runtime.snapshot()).__dict__
        if self.name == "browser_press":
            await page.locator(str(arguments["selector"])).first.press(str(arguments.get("key", "Enter")))
            return (await self.runtime.snapshot()).__dict__
        if self.name == "browser_back":
            return (await self.runtime.back()).__dict__
        raise ValueError(f"unsupported browser tool: {self.name}")


def register_browser_tools(registry: ToolRegistry) -> PlaywrightBrowser:
    runtime = PlaywrightBrowser(headless=False)
    for name, description, risk in (
        ("browser_open", "Open any permitted website visibly in TOM's browser.", Risk.LOW),
        ("browser_snapshot", "Observe the current browser page text and URL.", Risk.READ),
        ("browser_click", "Click a grounded browser selector.", Risk.LOW),
        ("browser_click_text", "Click a visible browser text target.", Risk.LOW),
        ("browser_fill", "Fill a grounded browser field.", Risk.LOW),
        ("browser_fill_label", "Fill a browser field by its accessible label.", Risk.LOW),
        ("browser_press", "Press a key on a grounded browser field.", Risk.LOW),
        ("browser_back", "Navigate back in the visible browser.", Risk.LOW),
    ):
        registry.register(BrowserRuntimeTool(name, description, risk, runtime))
    return runtime
