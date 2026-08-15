from tom.production import ProductionReadiness


def test_readiness_does_not_fake_missing_model() -> None:
    report = ProductionReadiness().report()
    names = {item["name"]: item for item in report["checks"]}
    assert "model" in names
    assert isinstance(names["model"]["configured"], bool)


def test_integration_registry_is_explicit() -> None:
    from tom.integration_registry import status

    rows = status()
    assert rows
    assert all("id" in row and "enabled" in row and "mode" in row for row in rows)
