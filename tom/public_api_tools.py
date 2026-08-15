from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .models import Risk
from .tools import ToolRegistry

TIMEOUT = httpx.Timeout(12.0, connect=5.0)
USER_AGENT = "TOM-Agent/2.0 (+https://github.com/Raghav549/TOM)"


async def _get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers=merged) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


@dataclass
class OpenMeteoWeatherTool:
    name: str = "api.weather"
    risk: Risk = Risk.READ
    description: str = "Get current/forecast weather from Open-Meteo."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        latitude = float(arguments["latitude"])
        longitude = float(arguments["longitude"])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("invalid coordinates")
        return await _get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "timezone": arguments.get("timezone", "auto"),
            },
        )


@dataclass
class NominatimGeocodeTool:
    name: str = "api.geocode"
    risk: Risk = Risk.READ
    description: str = "Geocode a place name using OpenStreetMap Nominatim."

    async def run(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(10, int(arguments.get("limit", 5))))
        return await _get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "jsonv2", "limit": limit},
        )


@dataclass
class FrankfurterCurrencyTool:
    name: str = "api.currency"
    risk: Risk = Risk.READ
    description: str = "Get current reference exchange rates from Frankfurter."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = str(arguments.get("base", "EUR")).upper()
        symbols = str(arguments.get("symbols", "USD")).upper()
        return await _get("https://api.frankfurter.app/latest", params={"from": base, "to": symbols})


@dataclass
class NagerHolidayTool:
    name: str = "api.holidays"
    risk: Risk = Risk.READ
    description: str = "Get public holidays for a country and year."

    async def run(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        country = str(arguments["country_code"]).upper()
        year = int(arguments.get("year"))
        if len(country) != 2 or not 1900 <= year <= 2200:
            raise ValueError("country_code must be ISO-2 and year must be valid")
        return await _get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}")


@dataclass
class RestCountriesTool:
    name: str = "api.countries"
    risk: Risk = Risk.READ
    description: str = "Find country metadata, currencies, languages and borders."

    async def run(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        safe_query = query.replace("/", "").replace("?", "")[:80]
        return await _get(f"https://restcountries.com/v3.1/name/{safe_query}")


@dataclass
class OpenLibraryBooksTool:
    name: str = "api.books"
    risk: Risk = Risk.READ
    description: str = "Search Open Library books and editions."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(20, int(arguments.get("limit", 10))))
        return await _get("https://openlibrary.org/search.json", params={"q": query, "limit": limit})


@dataclass
class CatFactTool:
    name: str = "api.cat_fact"
    risk: Risk = Risk.READ
    description: str = "Get a random cat fact."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await _get("https://catfact.ninja/fact")


@dataclass
class DogImageTool:
    name: str = "api.dog"
    risk: Risk = Risk.READ
    description: str = "Get a random dog image URL."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await _get("https://dog.ceo/api/breeds/image/random")


def register_public_api_tools(registry: ToolRegistry) -> None:
    for tool in (
        OpenMeteoWeatherTool(),
        NominatimGeocodeTool(),
        FrankfurterCurrencyTool(),
        NagerHolidayTool(),
        RestCountriesTool(),
        OpenLibraryBooksTool(),
        CatFactTool(),
        DogImageTool(),
    ):
        registry.register(tool)
