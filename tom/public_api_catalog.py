from __future__ import annotations

"""Typed capability catalogue for external API adapters.

The public-apis repository is a discovery directory, not an execution layer.
TOM only executes providers represented by a typed adapter with an explicit
risk classification and credential policy.
"""

from dataclasses import dataclass
from enum import StrEnum


class AuthMode(StrEnum):
    NONE = "none"
    API_KEY = "apiKey"
    OAUTH = "OAuth"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PublicAPIEntry:
    id: str
    category: str
    name: str
    description: str
    auth: AuthMode
    https: bool
    executable: bool = False
    adapter: str | None = None
    credential_env: str | None = None


CATALOG: tuple[PublicAPIEntry, ...] = (
    PublicAPIEntry("open-meteo", "Weather", "Open-Meteo", "Weather and forecast data", AuthMode.NONE, True, True, "api.weather"),
    PublicAPIEntry("nominatim", "Geocoding", "OpenStreetMap Nominatim", "Place search and geocoding", AuthMode.NONE, True, True, "api.geocode"),
    PublicAPIEntry("frankfurter", "Currency Exchange", "Frankfurter", "Reference exchange rates", AuthMode.NONE, True, True, "api.currency"),
    PublicAPIEntry("nager-date", "Calendar", "Nager.Date", "Public holidays by country and year", AuthMode.NONE, True, True, "api.holidays"),
    PublicAPIEntry("rest-countries", "Government", "REST Countries", "Country metadata, codes and currencies", AuthMode.NONE, True, True, "api.countries"),
    PublicAPIEntry("open-library", "Books", "Open Library", "Books and edition search", AuthMode.NONE, True, True, "api.books"),
    PublicAPIEntry("world-time", "Time", "WorldTimeAPI", "Current time by timezone", AuthMode.NONE, True, True, "api.time"),
    PublicAPIEntry("hacker-news", "News", "Hacker News API", "Current technology stories", AuthMode.NONE, True, True, "api.news"),
    PublicAPIEntry("coingecko", "Finance", "CoinGecko", "Cryptocurrency prices", AuthMode.NONE, True, True, "api.crypto"),
    PublicAPIEntry("github", "Development", "GitHub API", "Public repository search", AuthMode.NONE, True, True, "api.github"),
    PublicAPIEntry("spacex", "Space", "SpaceX API", "Launch data", AuthMode.NONE, True, True, "api.space"),
    PublicAPIEntry("cat-facts", "Animals", "Cat Facts", "Random cat facts", AuthMode.NONE, True, True, "api.cat_fact"),
    PublicAPIEntry("dog-ceo", "Animals", "Dog API", "Random dog images", AuthMode.NONE, True, True, "api.dog"),
    PublicAPIEntry("aviationstack", "Transportation", "Aviationstack", "Flight and aviation data", AuthMode.API_KEY, True, True, "api.flights", "TOM_AVIATIONSTACK_KEY"),
    PublicAPIEntry("serpstack", "Search", "Serpstack", "Search-engine result data", AuthMode.API_KEY, True, True, "api.search", "TOM_SERPSTACK_KEY"),
    PublicAPIEntry("marketstack", "Finance", "Marketstack", "Worldwide stock market data", AuthMode.API_KEY, True, True, "api.stocks", "TOM_MARKETSTACK_KEY"),
    PublicAPIEntry("mailboxlayer", "Email", "Mailboxlayer", "Email validation", AuthMode.API_KEY, True, True, "api.email_validate", "TOM_MAILBOXLAYER_KEY"),
    PublicAPIEntry("weatherstack", "Weather", "Weatherstack", "Weather data", AuthMode.API_KEY, True, False),
    PublicAPIEntry("google-calendar", "Calendar", "Google Calendar", "Calendar event management", AuthMode.OAUTH, True, False),
    PublicAPIEntry("google-gmail", "Email", "Gmail", "Email send/read operations", AuthMode.OAUTH, True, False),
)


def catalog() -> list[dict[str, object]]:
    return [entry.__dict__ for entry in CATALOG]


def executable_catalog() -> list[dict[str, object]]:
    return [entry.__dict__ for entry in CATALOG if entry.executable]


def configured_optional_catalog() -> list[dict[str, object]]:
    return [entry.__dict__ for entry in CATALOG if not entry.executable]
