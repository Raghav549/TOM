from __future__ import annotations

"""Machine-readable Public APIs capability catalogue for TOM.

The upstream public-apis project is a curated directory, not a runtime API.
TOM keeps a small, typed, policy-aware catalogue here and uses the upstream
README as the source of discovery. A provider becomes executable only when an
adapter below declares its endpoint, auth mode, risk and parser.
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


CATALOG: tuple[PublicAPIEntry, ...] = (
    PublicAPIEntry("open-meteo", "Weather", "Open-Meteo", "Weather and forecast data", AuthMode.NONE, True, True, "api.weather"),
    PublicAPIEntry("nominatim", "Geocoding", "OpenStreetMap Nominatim", "Place search and geocoding", AuthMode.NONE, True, True, "api.geocode"),
    PublicAPIEntry("frankfurter", "Currency Exchange", "Frankfurter", "Reference exchange rates", AuthMode.NONE, True, True, "api.currency"),
    PublicAPIEntry("nager-date", "Calendar", "Nager.Date", "Public holidays by country and year", AuthMode.NONE, True, True, "api.holidays"),
    PublicAPIEntry("rest-countries", "Government", "REST Countries", "Country metadata, codes and currencies", AuthMode.NONE, True, True, "api.countries"),
    PublicAPIEntry("open-library", "Books", "Open Library", "Books and edition search", AuthMode.NONE, True, True, "api.books"),
    PublicAPIEntry("cat-facts", "Animals", "Cat Facts", "Random cat facts", AuthMode.NONE, True, True, "api.cat_fact"),
    PublicAPIEntry("dog-ceo", "Animals", "Dog API", "Random dog images", AuthMode.NONE, True, True, "api.dog"),
    PublicAPIEntry("aviationstack", "Transportation", "Aviationstack", "Flight and aviation data", AuthMode.API_KEY, True, False),
    PublicAPIEntry("serpstack", "Search", "Serpstack", "Search-engine result data", AuthMode.API_KEY, True, False),
    PublicAPIEntry("marketstack", "Finance", "Marketstack", "Worldwide stock market data", AuthMode.API_KEY, True, False),
    PublicAPIEntry("mailboxlayer", "Email", "Mailboxlayer", "Email validation", AuthMode.API_KEY, True, False),
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
