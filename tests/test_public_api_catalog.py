from tom.public_api_catalog import catalog, executable_catalog
from tom.public_api_tools import (
    DogImageTool,
    FrankfurterCurrencyTool,
    NagerHolidayTool,
    NominatimGeocodeTool,
    OpenLibraryBooksTool,
    OpenMeteoWeatherTool,
    RestCountriesTool,
)


def test_catalog_has_safe_executable_high_value_adapters():
    ids = {item["id"] for item in executable_catalog()}
    assert {"open-meteo", "nominatim", "frankfurter", "nager-date", "rest-countries", "open-library"} <= ids


def test_catalog_marks_credentialed_providers_non_executable_by_default():
    items = {item["id"]: item for item in catalog()}
    assert items["aviationstack"]["auth"] == "apiKey"
    assert items["aviationstack"]["executable"] is False
    assert items["google-calendar"]["auth"] == "OAuth"
    assert items["google-calendar"]["executable"] is False


def test_tool_names_are_stable():
    names = {
        OpenMeteoWeatherTool().name,
        NominatimGeocodeTool().name,
        FrankfurterCurrencyTool().name,
        NagerHolidayTool().name,
        RestCountriesTool().name,
        OpenLibraryBooksTool().name,
        DogImageTool().name,
    }
    assert "api.weather" in names
    assert "api.holidays" in names
    assert "api.countries" in names
    assert "api.books" in names
