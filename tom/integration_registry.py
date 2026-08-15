from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationStatus:
    id: str
    enabled: bool
    mode: str
    detail: str


INTEGRATIONS = {
    "weather": "TOM_API_WEATHER_ENABLED",
    "geocoding": "TOM_API_GEOCODING_ENABLED",
    "currency": "TOM_API_CURRENCY_ENABLED",
    "maps": "TOM_MAPS_PROVIDER",
    "flights": "TOM_FLIGHTS_PROVIDER",
    "places": "TOM_PLACES_PROVIDER",
    "news": "TOM_NEWS_PROVIDER",
    "calendar": "TOM_CALENDAR_PROVIDER",
    "email": "TOM_EMAIL_PROVIDER",
    "messaging": "TOM_MESSAGING_PROVIDER",
    "finance": "TOM_FINANCE_PROVIDER",
    "transport": "TOM_TRANSPORT_PROVIDER",
    "payments": "TOM_PAYMENTS_PROVIDER",
}


def status() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for integration, env_name in INTEGRATIONS.items():
        value = os.getenv(env_name, "").strip()
        if value.lower() in {"1", "true", "yes", "enabled"}:
            result.append(IntegrationStatus(integration, True, "public_or_local", f"enabled by {env_name}").__dict__)
        elif value:
            result.append(IntegrationStatus(integration, True, "provider_configured", f"provider configured: {env_name}").__dict__)
        else:
            result.append(IntegrationStatus(integration, False, "unconfigured", f"set {env_name} after selecting a real provider").__dict__)
    return result
