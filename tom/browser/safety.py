from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class NavigationDecision:
    allowed: bool
    reason: str


class BrowserSafetyPolicy:
    """Conservative browser navigation policy for agent-controlled sessions."""

    def __init__(self, *, allowed_hosts: set[str] | None = None) -> None:
        self.allowed_hosts = {h.lower().strip('.') for h in (allowed_hosts or set()) if h.strip()}

    def check_navigation(self, url: str) -> NavigationDecision:
        try:
            parsed = urlparse(url)
        except ValueError:
            return NavigationDecision(False, "invalid_url")

        if parsed.scheme not in {"http", "https"}:
            return NavigationDecision(False, "unsupported_scheme")
        if not parsed.hostname:
            return NavigationDecision(False, "missing_host")
        if parsed.username or parsed.password:
            return NavigationDecision(False, "embedded_credentials_blocked")

        host = parsed.hostname.lower().strip('.')
        if self.allowed_hosts and host not in self.allowed_hosts:
            return NavigationDecision(False, "host_not_allowlisted")
        return NavigationDecision(True, "allowed")
