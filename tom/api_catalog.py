from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import httpx


PUBLIC_APIS_README = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"


@dataclass(frozen=True)
class ApiEntry:
    name: str
    url: str
    description: str
    auth: str
    https: bool
    cors: str


class ApiCatalog:
    """Discovery-only catalog for public APIs; execution happens through explicit adapters."""

    def __init__(self, entries: Iterable[ApiEntry] = ()) -> None:
        self._entries = list(entries)

    @property
    def entries(self) -> tuple[ApiEntry, ...]:
        return tuple(self._entries)

    def search(self, query: str, *, auth: str | None = None, https_only: bool = True) -> list[ApiEntry]:
        tokens = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2}
        ranked: list[tuple[int, ApiEntry]] = []
        for entry in self._entries:
            if https_only and not entry.https:
                continue
            if auth and entry.auth.lower() != auth.lower():
                continue
            haystack = f"{entry.name} {entry.description}".lower()
            score = sum(2 if token in entry.name.lower() else 1 for token in tokens if token in haystack)
            if score:
                ranked.append((score, entry))
        return [entry for _, entry in sorted(ranked, key=lambda item: (-item[0], item[1].name.lower()))]

    @classmethod
    def parse_readme(cls, text: str) -> ApiCatalog:
        entries: list[ApiEntry] = []
        # Current public-apis format is a Markdown table. Keep parsing deliberately strict.
        row = re.compile(r"^\|\s*\[([^\]]+)\]\((https?://[^)]+)\)\s*\|\s*(.*?)\s*\|\s*([^|]+?)\s*\|\s*(Yes|No)\s*\|\s*([^|]+?)\s*\|", re.I)
        for line in text.splitlines():
            match = row.match(line.strip())
            if not match:
                continue
            name, url, description, auth, https, cors = match.groups()
            entries.append(ApiEntry(name.strip(), url.strip(), description.strip(), auth.strip(), https.lower() == "yes", cors.strip()))
        return cls(entries)

    @classmethod
    async def from_public_apis(cls, *, timeout: float = 15.0) -> ApiCatalog:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(PUBLIC_APIS_README)
            response.raise_for_status()
            return cls.parse_readme(response.text)


class ApiAdapterRegistry:
    """Only explicitly registered adapters may execute an external API."""

    def __init__(self) -> None:
        self._adapters: dict[str, object] = {}

    def register(self, api_name: str, adapter: object) -> None:
        key = api_name.strip().lower()
        if not key:
            raise ValueError("api name cannot be empty")
        self._adapters[key] = adapter

    def get(self, api_name: str) -> object:
        key = api_name.strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise LookupError(f"no approved adapter for API: {api_name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
