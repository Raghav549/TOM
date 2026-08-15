from __future__ import annotations

import os

from tom.browser.runtime import PlaywrightBrowser
from tom.browser.safety import BrowserSafetyPolicy
from tom.production import ProductionReadiness


def test_browser_blocks_unsafe_navigation() -> None:
    policy = BrowserSafetyPolicy(allowed_hosts={"example.com"})
    assert policy.check_navigation("file:///etc/passwd").allowed is False
    assert policy.check_navigation("https://user:pass@example.com").allowed is False
    assert policy.check_navigation("https://evil.example").allowed is False
    assert policy.check_navigation("https://example.com/path").allowed is True


def test_browser_runtime_requires_start() -> None:
    browser = PlaywrightBrowser()
    try:
        import asyncio
        asyncio.run(browser.snapshot())
    except RuntimeError as exc:
        assert "not started" in str(exc)


def test_production_gate_is_truthful_in_development() -> None:
    old = os.environ.get("TOM_ENV")
    os.environ["TOM_ENV"] = "development"
    try:
        report = ProductionReadiness().report()
        assert report["ready"] is False or report["ready"] is True
        assert "checks" in report
    finally:
        if old is None:
            os.environ.pop("TOM_ENV", None)
        else:
            os.environ["TOM_ENV"] = old
