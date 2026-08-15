from pathlib import Path

import pytest

from tom.credentials import CredentialManager
from tom.integration_tools import GoogleCalendarCreateTool, GmailSendTool, GooglePlacesSearchTool, TwilioSmsTool, register_integration_tools
from tom.tools import ToolRegistry


def test_integration_tools_bind_to_runtime_registry(tmp_path: Path) -> None:
    registry = ToolRegistry({})
    oauth = register_integration_tools(registry, CredentialManager(tmp_path))
    assert oauth.connected() is False
    assert "google.calendar_list" in registry.tools
    assert "google.calendar_create" in registry.tools
    assert "google.gmail_search" in registry.tools
    assert "google.gmail_send" in registry.tools
    assert "maps.places_search" in registry.tools
    assert "maps.route" in registry.tools
    assert "communication.sms_send" in registry.tools
    assert registry.tools["google.calendar_create"].risk.value == "high"
    assert registry.tools["google.gmail_send"].risk.value == "high"
    assert registry.tools["communication.sms_send"].risk.value == "high"


def test_credential_manager_encrypts_persistent_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOM_CREDENTIAL_MASTER_KEY", "test-only-master-secret")
    manager = CredentialManager(tmp_path)
    manager.set("google", {"access_token": "token", "refresh_token": "refresh"})
    assert manager.get("google") == {"access_token": "token", "refresh_token": "refresh"}
    assert b"refresh" not in (tmp_path / "credentials.enc").read_bytes()


def test_side_effect_tools_require_credentials_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOM_GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("TOM_TWILIO_ACCOUNT_SID", raising=False)
    with pytest.raises(RuntimeError, match="TOM_GOOGLE_MAPS_API_KEY"):
        import asyncio
        asyncio.run(GooglePlacesSearchTool().run({"query": "airport"}))
    with pytest.raises(RuntimeError, match="TOM_TWILIO_ACCOUNT_SID"):
        import asyncio
        asyncio.run(TwilioSmsTool().run({"to": "+10000000000", "body": "test"}))


def test_google_write_tools_are_high_risk() -> None:
    assert GoogleCalendarCreateTool().risk.value == "high"
    assert GmailSendTool().risk.value == "high"
