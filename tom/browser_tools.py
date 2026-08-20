from __future__ import annotations

from dataclasses import dataclass
import os
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
        if self.name == "browser_screenshot":
            return {"path": await self.runtime.screenshot(arguments.get("path"), full_page=bool(arguments.get("full_page", False)))}
        if self.name == "browser_click":
            return (await self.runtime.click(str(arguments["selector"]))).__dict__
        if self.name == "browser_click_text":
            await page.get_by_text(str(arguments["text"]), exact=bool(arguments.get("exact", False))).first.click()
            return (await self.runtime.snapshot()).__dict__
        if self.name == "browser_click_role":
            return (await self.runtime.click_role(str(arguments["role"]), str(arguments["name"]), bool(arguments.get("exact", False)))).__dict__
        if self.name == "browser_fill":
            return (await self.runtime.fill(str(arguments["selector"]), str(arguments["value"]))).__dict__
        if self.name == "browser_fill_label":
            return (await self.runtime.fill_label(str(arguments["label"]), str(arguments["value"]), bool(arguments.get("exact", False)))).__dict__
        if self.name == "browser_press":
            return (await self.runtime.press(str(arguments["selector"]), str(arguments.get("key", "Enter")))).__dict__
        if self.name == "browser_press_key":
            return (await self.runtime.press_key(str(arguments.get("key", "Enter")))).__dict__
        if self.name == "browser_scroll":
            return (await self.runtime.scroll(amount=int(arguments.get("amount", 700)), selector=arguments.get("selector"))).__dict__
        if self.name == "browser_check":
            return (await self.runtime.check(str(arguments["selector"]))).__dict__
        if self.name == "browser_uncheck":
            return (await self.runtime.uncheck(str(arguments["selector"]))).__dict__
        if self.name == "browser_select":
            return (await self.runtime.select(str(arguments["selector"]), str(arguments["value"]))).__dict__
        if self.name == "browser_hover":
            return (await self.runtime.hover(str(arguments["selector"]))).__dict__
        if self.name == "browser_wait":
            return (await self.runtime.wait_for(arguments.get("selector"), int(arguments.get("timeout_ms", 1000)))).__dict__
        if self.name == "browser_download":
            return await self.runtime.download(str(arguments["selector"]), filename=arguments.get("filename"))
        if self.name == "browser_reload":
            return (await self.runtime.reload()).__dict__
        if self.name == "browser_back":
            return (await self.runtime.back()).__dict__
        raise ValueError(f"unsupported browser tool: {self.name}")


def register_browser_tools(registry: ToolRegistry) -> PlaywrightBrowser:
    default_headless = "true" if os.getenv("TOM_ENV", "development").lower() == "production" else "false"
    headless = os.getenv("TOM_BROWSER_HEADLESS", default_headless).lower() in {"1", "true", "yes", "on"}
    runtime = PlaywrightBrowser(
        headless=headless,
        download_dir=os.getenv("TOM_BROWSER_DOWNLOAD_DIR", ".tom-data/downloads"),
    )
    definitions = (
        ("browser_open", "Open any permitted website visibly in TOM's browser.", Risk.LOW),
        ("browser_snapshot", "Observe the current browser page text and URL.", Risk.READ),
        ("browser_screenshot", "Capture fresh browser pixels for grounding and verification.", Risk.READ),
        ("browser_click", "Click a grounded browser selector.", Risk.LOW),
        ("browser_click_text", "Click a visible browser text target.", Risk.LOW),
        ("browser_click_role", "Click a browser target using its accessible ARIA role and name.", Risk.LOW),
        ("browser_fill", "Fill a grounded browser field.", Risk.LOW),
        ("browser_fill_label", "Fill a browser field by accessible label.", Risk.LOW),
        ("browser_press", "Press a key on a grounded browser field.", Risk.LOW),
        ("browser_press_key", "Press a global keyboard key in the visible browser.", Risk.LOW),
        ("browser_scroll", "Scroll or bring a grounded browser element into view.", Risk.LOW),
        ("browser_check", "Check a grounded checkbox.", Risk.LOW),
        ("browser_uncheck", "Uncheck a grounded checkbox.", Risk.LOW),
        ("browser_select", "Select a grounded option from a browser select.", Risk.LOW),
        ("browser_hover", "Hover a grounded browser target.", Risk.LOW),
        ("browser_wait", "Wait for a grounded page condition to stabilize.", Risk.READ),
        ("browser_download", "Download a visible browser artifact into TOM's controlled data directory.", Risk.LOW),
        ("browser_reload", "Reload the current visible browser page.", Risk.LOW),
        ("browser_back", "Navigate back in the visible browser.", Risk.LOW),
    )
    for name, description, risk in definitions:
        registry.register(BrowserRuntimeTool(name, description, risk, runtime))
    return runtime
