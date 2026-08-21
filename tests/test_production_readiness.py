from __future__ import annotations

import pytest

from tom.production import ProductionReadiness


def test_readiness_does_not_fake_missing_model() -> None:
    checks = ProductionReadiness().checks()
    names = {item.name: item for item in checks}
    assert "model" in names
    assert isinstance(names["model"].configured, bool)


def test_integration_registry_is_explicit() -> None:
    from tom.integration_registry import status

    rows = status()
    assert rows
    assert all("id" in row and "enabled" in row and "mode" in row for row in rows)


@pytest.mark.asyncio
async def test_live_device_is_operational_not_readiness_blocker(monkeypatch, tmp_path):
    monkeypatch.setenv("TOM_ENV", "production")
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_DEVICE_SECRETS_JSON", '{"device":"secret"}')
    monkeypatch.setenv("TOM_LLM_ENABLED", "false")
    monkeypatch.setenv("TOM_TTS_ENGINE", "disabled")
    monkeypatch.setenv("TOM_NEURAL_VAD", "false")
    monkeypatch.delenv("TOM_REQUIRED_CAPABILITIES", raising=False)

    readiness = ProductionReadiness()
    report = await readiness.probe(browser=None, device_sessions={})

    assert report["ready"] is True
    assert report["operational"]["device_connected"] is False
    assert report["failed_required_capabilities"] == []
    assert set(report["required_capabilities"]) == {"device_auth", "persistent_data"}


@pytest.mark.asyncio
async def test_optional_failures_are_reported_as_degraded_not_unready(monkeypatch, tmp_path):
    monkeypatch.setenv("TOM_ENV", "production")
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_DEVICE_SECRETS_JSON", '{"device":"secret"}')
    monkeypatch.setenv("TOM_LLM_ENABLED", "true")
    monkeypatch.delenv("TOM_LLM_API_KEY", raising=False)
    monkeypatch.setenv("TOM_TTS_ENGINE", "qwen3")
    monkeypatch.delenv("TOM_QWEN3_TTS_STREAM_URL", raising=False)
    monkeypatch.delenv("TOM_QWEN3_TTS_MODEL_DIR", raising=False)
    monkeypatch.setenv("TOM_NEURAL_VAD", "false")
    monkeypatch.delenv("TOM_REQUIRED_CAPABILITIES", raising=False)

    readiness = ProductionReadiness()
    report = await readiness.probe(browser=None, device_sessions=None)

    assert report["ready"] is True
    assert "model" in report["degraded_capabilities"]
    assert "tts" in report["degraded_capabilities"]


@pytest.mark.asyncio
async def test_explicit_required_capability_can_block_readiness(monkeypatch, tmp_path):
    monkeypatch.setenv("TOM_ENV", "production")
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_DEVICE_SECRETS_JSON", '{"device":"secret"}')
    monkeypatch.setenv("TOM_LLM_ENABLED", "true")
    monkeypatch.delenv("TOM_LLM_API_KEY", raising=False)
    monkeypatch.setenv("TOM_TTS_ENGINE", "disabled")
    monkeypatch.setenv("TOM_NEURAL_VAD", "false")
    monkeypatch.setenv("TOM_REQUIRED_CAPABILITIES", "device_auth,persistent_data,model")

    readiness = ProductionReadiness()
    report = await readiness.probe(browser=None, device_sessions=None)

    assert report["ready"] is False
    assert report["failed_required_capabilities"] == ["model"]
