from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from tom.api import app as app_module

    with TestClient(app_module.app) as client:
        yield client


def test_health_reports_package_version(client: TestClient) -> None:
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["version"] and payload["version"] != "1.0.0"


def test_agent_endpoint_returns_pending_approval_for_side_effects(client: TestClient) -> None:
    response = client.post("/v1/agent", json={"message": "send a message to Rahul saying hi", "conversation_id": "api-t1"})
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "api-t1"
    assert body["reply"]
    assert body["pending_approval"], "high-risk steps must wait for approval"

    pending = client.get("/v1/agent/api-t1/pending").json()
    assert pending["pending_approval"][0]["name"] == body["pending_approval"][0]["name"]

    task = client.get("/v1/tasks/api-t1")
    assert task.status_code == 200
    assert task.json()["goal"]


def test_agent_approve_rejects_unknown_index(client: TestClient) -> None:
    response = client.post("/v1/agent/approve", json={"conversation_id": "does-not-exist", "tool_index": 3})
    assert response.status_code == 404


def test_unknown_task_is_404(client: TestClient) -> None:
    assert client.get("/v1/tasks/nope").status_code == 404


def test_profile_roundtrip(client: TestClient) -> None:
    before = client.get("/v1/profile").json()
    assert before["name"]
    updated = client.post("/v1/profile", json={"name": "Nova", "interests": ["chess", " music "], "commentary_enabled": False}).json()
    assert updated["name"] == "Nova"
    assert updated["interests"] == ["chess", "music"]
    assert updated["commentary_enabled"] is False
    client.post("/v1/profile", json={"name": before["name"], "commentary_enabled": before["commentary_enabled"]})
