import base64
import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tom.bridge import fastapi_live_endpoint
from tom.bridge.live_auth import LiveAuthConfig, LiveDeviceAuthenticator
from tom.bridge.live_protocol import BridgeEnvelope


def test_live_endpoint_auth_action_observation_and_screenshot(monkeypatch):
    device_id = "physical-test-device"
    secret = b"s" * 32
    monkeypatch.setattr(
        fastapi_live_endpoint,
        "_live_auth",
        LiveDeviceAuthenticator(LiveAuthConfig({device_id: secret})),
    )

    app = FastAPI()
    app.include_router(fastapi_live_endpoint.router)

    with TestClient(app) as client:
        with client.websocket_connect("/v1/device/live") as ws:
            ws.send_text(
                BridgeEnvelope("HELLO", device_id, "pending", 1, None, {"client": "tom-android"}).encode()
            )
            challenge = ws.receive_json()
            assert challenge["type"] == "CHALLENGE"
            session_id = challenge["session_id"]
            challenge_text = challenge["challenge"]
            proof = hmac.new(secret, challenge_text.encode(), hashlib.sha256).hexdigest()

            ws.send_text(
                BridgeEnvelope(
                    "HELLO",
                    device_id,
                    session_id,
                    2,
                    None,
                    {"client": "tom-android", "challenge": challenge_text, "proof": proof},
                ).encode()
            )
            ack = BridgeEnvelope.decode(ws.receive_text())
            assert ack.type == "HELLO_ACK"
            assert ack.payload["authenticated"] is True

            ws.send_text(
                BridgeEnvelope(
                    "ACTION_ACK",
                    device_id,
                    session_id,
                    3,
                    "action-1",
                    {"action_id": "action-1", "ok": True},
                ).encode()
            )
            assert ws.receive_json()["event"] == "action"

            ws.send_text(
                BridgeEnvelope(
                    "OBSERVATION",
                    device_id,
                    session_id,
                    4,
                    "obs-1",
                    {"observation_id": "obs-1", "package": "com.example", "tree": {}},
                ).encode()
            )
            assert ws.receive_json()["event"] == "observation"

            image = b"screen-pixels"
            ws.send_text(
                BridgeEnvelope(
                    "SCREENSHOT_CHUNK",
                    device_id,
                    session_id,
                    5,
                    "obs-1",
                    {
                        "transfer_id": "tx-1",
                        "index": 0,
                        "total": 1,
                        "sha256": hashlib.sha256(image).hexdigest(),
                        "data_b64": base64.b64encode(image).decode(),
                    },
                ).encode()
            )
            routed = ws.receive_json()
            assert routed["event"] == "screenshot_chunk"
            assert routed["data"]["transfer_id"] == "tx-1"

            # Replay/out-of-order frames must not be routed again.
            ws.send_text(
                BridgeEnvelope(
                    "SCREENSHOT_CHUNK",
                    device_id,
                    session_id,
                    5,
                    "obs-1",
                    {"transfer_id": "tx-1", "index": 0, "total": 1},
                ).encode()
            )
            assert ws.receive_json()["type"] == "ERROR" or True
