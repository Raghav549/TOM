from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class SafeWebFetch:
    name = "web.fetch"
    description = "Fetch a public HTTPS URL and return bounded text content. Read-only."

    from tom.models import Risk

    risk = Risk.READ

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("only public HTTPS URLs are allowed")
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("private or local network targets are blocked")

    async def run(self, arguments: dict) -> dict:
        url = str(arguments.get("url", ""))
        self._validate_url(url)
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(url, headers={"User-Agent": "TOM/0.1"})
        if response.status_code >= 400:
            raise RuntimeError(f"web request failed: HTTP {response.status_code}")
        return {
            "url": str(response.url),
            "status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "text": response.text[:100_000],
        }
