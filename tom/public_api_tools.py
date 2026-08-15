from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .models import Risk
from .tools import ToolRegistry


@dataclass
class OpenMeteoWeatherTool:
    name: str = "api.weather"
    risk: Risk = Risk.READ
    description: str = "Get current/forecast weather from Open-Meteo."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        latitude = float(arguments["latitude"])
        longitude = float(arguments["longitude"])
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": arguments.get("timezone", "auto"),
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            return response.json()


@dataclass
class NominatimGeocodeTool:
    name: str = "api.geocode"
    risk: Risk = Risk.READ
    description: str = "Geocode a place name using OpenStreetMap Nominatim."

    async def run(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "TOM-Agent/2.0"}) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "jsonv2", "limit": int(arguments.get("limit", 5))},
            )
            response.raise_for_status()
            return response.json()


@dataclass
class FrankfurterCurrencyTool:
    name: str = "api.currency"
    risk: Risk = Risk.READ
    description: str = "Get current reference exchange rates from Frankfurter."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = str(arguments.get("base", "EUR")).upper()
        symbols = str(arguments.get("symbols", "USD")).upper()
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": base, "to": symbols},
            )
            response.raise_for_status()
            return response.json()


def register_public_api_tools(registry: ToolRegistry) -> None:
    for tool in (OpenMeteoWeatherTool(), NominatimGeocodeTool(), FrankfurterCurrencyTool()):
        registry.register(tool)
