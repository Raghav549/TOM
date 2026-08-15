from __future__ import annotations

from fastapi.testclient import TestClient


def test_credential_status_hides_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_CREDENTIAL_MASTER_KEY", "test-master-secret")
    from tom.api.app import app

    client = TestClient(app)
    response = client.get("/v1/credentials/status")
    assert response.status_code == 200
    body = response.json()
    assert body["vault"]["configured"] is True
    assert "api_key" not in str(body)


def test_credential_provisioning_requires_server_token(tmp_path, monkeypatch):
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_CREDENTIAL_MASTER_KEY", "test-master-secret")
    monkeypatch.setenv("TOM_CREDENTIAL_PROVISION_TOKEN", "provision-secret")
    from tom.api.app import app

    client = TestClient(app)
    payload = {"provider": "google_maps", "credentials": {"api_key": "maps-secret"}}
    assert client.post("/v1/credentials", json=payload).status_code == 401
    response = client.post("/v1/credentials", json=payload, headers={"Authorization": "Bearer provision-secret"})
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "maps-secret" not in response.text


def test_google_connect_requires_oauth_configuration(monkeypatch):
    monkeypatch.delenv("TOM_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOM_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TOM_GOOGLE_REDIRECT_URI", raising=False)
    from tom.api.app import app

    client = TestClient(app)
    response = client.get("/v1/integrations/google/connect")
    assert response.status_code == 503
    assert "TOM_GOOGLE_CLIENT_ID" in response.text


def test_google_status_is_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_CREDENTIAL_MASTER_KEY", "test-master-secret")
    from tom.api.app import app

    client = TestClient(app)
    response = client.get("/v1/integrations/google/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert "access_token" not in response.text


def test_oauth_state_is_signed(monkeypatch, tmp_path):
    monkeypatch.setenv("TOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TOM_CREDENTIAL_MASTER_KEY", "test-master-secret")
    monkeypatch.setenv("TOM_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOM_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("TOM_GOOGLE_REDIRECT_URI", "http://localhost:8787/v1/integrations/google/callback")
    from tom.credentials import CredentialManager
    from tom.google_oauth import GoogleOAuth

    oauth = GoogleOAuth(CredentialManager(tmp_path))
    flow = oauth.begin()
    assert flow["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    oauth._validate_state(flow["state"])
    try:
        oauth._validate_state(flow["state"] + "x")
    except RuntimeError:
        pass
    else:
        raise AssertionError("tampered OAuth state was accepted")
