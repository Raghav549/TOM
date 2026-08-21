import asyncio

from tom.production import CapabilityCheck, ProductionReadiness


def test_disconnected_android_device_is_operational_status_not_readiness_failure(monkeypatch):
    readiness = ProductionReadiness()
    monkeypatch.setattr(
        readiness,
        "checks",
        lambda: [
            CapabilityCheck("model", True, "ok"),
            CapabilityCheck("device_auth", True, "configured"),
            CapabilityCheck("persistent_data", True, "writable"),
        ],
    )

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(readiness, "_probe_llm", no_op)
    monkeypatch.setattr(readiness, "_probe_tts", no_op)
    monkeypatch.setattr(readiness, "_probe_local_models", no_op)
    monkeypatch.setattr(readiness, "_probe_browser", no_op)
    monkeypatch.setattr(readiness, "_probe_persistence", lambda *_args, **_kwargs: None)

    report = asyncio.run(readiness.probe(device_sessions=[]))

    assert report["ready"] is True
    assert report["operational"] == {"device_connected": False}
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["device_auth"]["configured"] is True
    assert checks["device_connected"]["configured"] is False


def test_connected_android_device_is_reported_as_operational(monkeypatch):
    readiness = ProductionReadiness()
    monkeypatch.setattr(readiness, "checks", lambda: [CapabilityCheck("model", True, "ok")])

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(readiness, "_probe_llm", no_op)
    monkeypatch.setattr(readiness, "_probe_tts", no_op)
    monkeypatch.setattr(readiness, "_probe_local_models", no_op)
    monkeypatch.setattr(readiness, "_probe_browser", no_op)
    monkeypatch.setattr(readiness, "_probe_persistence", lambda *_args, **_kwargs: None)

    report = asyncio.run(readiness.probe(device_sessions={"android-1": object()}))

    assert report["ready"] is True
    assert report["operational"] == {"device_connected": True}
