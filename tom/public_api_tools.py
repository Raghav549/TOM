from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .models import Risk
from .tools import ToolRegistry

TIMEOUT = httpx.Timeout(12.0, connect=5.0)
USER_AGENT = "TOM-Agent/2.0 (+https://github.com/Raghav549/TOM)"


async def _get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers=merged) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"provider credential not configured: {name}")
    return value


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
                "hourly": "temperature_2m,precipitation_probability,weather_code",
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
            params={"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1},
            headers={"Accept-Language": str(arguments.get("language", "en"))},
        )


@dataclass
class FrankfurterCurrencyTool:
    name: str = "api.currency"
    risk: Risk = Risk.READ
    description: str = "Get reference exchange rates from Frankfurter."

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
class WorldTimeTool:
    name: str = "api.time"
    risk: Risk = Risk.READ
    description: str = "Get current local time for an IANA timezone."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        timezone = str(arguments["timezone"]).strip()
        if not timezone or ".." in timezone or len(timezone) > 80:
            raise ValueError("invalid timezone")
        return await _get(f"https://worldtimeapi.org/api/timezone/{timezone}")


@dataclass
class HackerNewsTool:
    name: str = "api.news"
    risk: Risk = Risk.READ
    description: str = "Get current Hacker News stories and item details."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        mode = str(arguments.get("mode", "top"))
        if mode not in {"top", "new", "best", "ask", "show", "job"}:
            raise ValueError("unsupported Hacker News mode")
        if mode in {"show", "job"} and arguments.get("id"):
            item = await _get(f"https://hacker-news.firebaseio.com/v0/item/{int(arguments['id'])}.json")
            return {"item": item}
        ids = await _get(f"https://hacker-news.firebaseio.com/v0/{mode}stories.json")
        limit = max(1, min(20, int(arguments.get("limit", 10))))
        items = []
        for item_id in ids[:limit]:
            item = await _get(f"https://hacker-news.firebaseio.com/v0/item/{int(item_id)}.json")
            if item:
                items.append(item)
        return {"mode": mode, "items": items}


@dataclass
class CoinGeckoPriceTool:
    name: str = "api.crypto"
    risk: Risk = Risk.READ
    description: str = "Get cryptocurrency prices from CoinGecko."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ids = str(arguments["ids"]).strip()
        currencies = str(arguments.get("currencies", "usd")).strip().lower()
        if not ids:
            raise ValueError("ids is required")
        return await _get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids[:500], "vs_currencies": currencies[:100]},
        )


@dataclass
class GitHubSearchTool:
    name: str = "api.github"
    risk: Risk = Risk.READ
    description: str = "Search public GitHub repositories."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(10, int(arguments.get("limit", 5))))
        return await _get(
            "https://api.github.com/search/repositories",
            params={"q": query, "per_page": limit},
            headers={"Accept": "application/vnd.github+json"},
        )


@dataclass
class SpaceXLaunchTool:
    name: str = "api.space"
    risk: Risk = Risk.READ
    description: str = "Get recent and upcoming SpaceX launches."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        upcoming = bool(arguments.get("upcoming", True))
        endpoint = "upcoming" if upcoming else "latest"
        return await _get(f"https://api.spacexdata.com/v4/launches/{endpoint}")


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


@dataclass
class AviationstackTool:
    name: str = "api.flights"
    risk: Risk = Risk.READ
    description: str = "Query aviation/flight data when TOM_AVIATIONSTACK_KEY is configured."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = _required_env("TOM_AVIATIONSTACK_KEY")
        params = {k: v for k, v in arguments.items() if k in {"flight_date", "dep_iata", "arr_iata", "flight_status", "limit"}}
        params["access_key"] = key
        return await _get("https://api.aviationstack.com/v1/flights", params=params)


@dataclass
class MarketstackTool:
    name: str = "api.stocks"
    risk: Risk = Risk.READ
    description: str = "Query stock market data when TOM_MARKETSTACK_KEY is configured."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = _required_env("TOM_MARKETSTACK_KEY")
        symbol = str(arguments["symbol"]).upper()
        return await _get(
            "https://api.marketstack.com/v1/eod/latest",
            params={"access_key": key, "symbols": symbol},
        )


@dataclass
class SerpstackTool:
    name: str = "api.search"
    risk: Risk = Risk.READ
    description: str = "Search-engine results when TOM_SERPSTACK_KEY is configured."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = _required_env("TOM_SERPSTACK_KEY")
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        return await _get("https://api.serpstack.com/search", params={"access_key": key, "query": query})


@dataclass
class MailboxlayerTool:
    name: str = "api.email_validate"
    risk: Risk = Risk.READ
    description: str = "Validate an email address when TOM_MAILBOXLAYER_KEY is configured."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = _required_env("TOM_MAILBOXLAYER_KEY")
        email = str(arguments["email"]).strip()
        if not email or len(email) > 320:
            raise ValueError("valid email is required")
        return await _get("https://apilayer.net/api/check", params={"access_key": key, "email": email})


def register_public_api_tools(registry: ToolRegistry) -> None:
    for tool in (
        OpenMeteoWeatherTool(),
        NominatimGeocodeTool(),
        FrankfurterCurrencyTool(),
        NagerHolidayTool(),
        RestCountriesTool(),
        OpenLibraryBooksTool(),
        WorldTimeTool(),
        HackerNewsTool(),
        CoinGeckoPriceTool(),
        GitHubSearchTool(),
        SpaceXLaunchTool(),
        CatFactTool(),
        DogImageTool(),
        AviationstackTool(),
        MarketstackTool(),
        SerpstackTool(),
        MailboxlayerTool(),
    ):
        registry.register(tool)
