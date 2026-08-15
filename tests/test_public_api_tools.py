from tom.public_api_catalog import executable_catalog
from tom.public_api_tools import (
    AviationstackTool,
    CoinGeckoPriceTool,
    FrankfurterCurrencyTool,
    GitHubSearchTool,
    HackerNewsTool,
    OpenMeteoWeatherTool,
    WorldTimeTool,
    register_public_api_tools,
)
from tom.tools import ToolRegistry


def test_expanded_catalog_contains_core_integrations() -> None:
    names = {entry["adapter"] for entry in executable_catalog()}
    assert {"api.weather", "api.geocode", "api.currency", "api.holidays"} <= names
    assert {"api.time", "api.news", "api.crypto", "api.github"} <= names
    assert "api.flights" not in names


def test_registry_registers_public_api_tools() -> None:
    registry = ToolRegistry({})
    register_public_api_tools(registry)
    names = set(registry.tools)
    assert "api.weather" in names
    assert "api.time" in names
    assert "api.news" in names
    assert "api.github" in names
    assert "api.flights" in names


def test_provider_validation_is_local() -> None:
    assert OpenMeteoWeatherTool().name == "api.weather"
    assert FrankfurterCurrencyTool().name == "api.currency"
    assert WorldTimeTool().name == "api.time"
    assert HackerNewsTool().name == "api.news"
    assert CoinGeckoPriceTool().name == "api.crypto"
    assert GitHubSearchTool().name == "api.github"


def test_key_provider_never_embeds_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOM_AVIATIONSTACK_KEY", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="TOM_AVIATIONSTACK_KEY"):
        __import__("asyncio").run(AviationstackTool().run({}))
