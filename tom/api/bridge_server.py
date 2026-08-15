from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


@dataclass
class DeviceSession:
    device_id: str
    websocket: WebSocket
    last_sequence: int = 0
    connected: bool = True


class AndroidBridgeHub:
    """In-memory live Android sessions; durable identity remains outside the socket."""

    def __init__(self) -> None:
        self.sessions: dict[str, DeviceSession] = {}
        self.lock = asyncio.Lock()

    async def attach(self, device_id: str, websocket: WebSocket) -> DeviceSession:
        async with self.lock:
            old = self.sessions.get(device_id)
            if old:
                old.connected = False
                try:
                    await old.websocket.close(code=4001, reason="replaced")
                except Exception:
                    pass
            session = DeviceSession(device_id=device_id, websocket=websocket)
            self.sessions[device_id] = session
            return session

    async def detach(self, device_id: str) -> None:
        async with self.lock:
            session = self.sessions.get(device_id)
            if session:
                session.connected = False
                self.sessions.pop(device_id, None)

    async def send(self, device_id: str, message: dict[str, Any]) -> bool:
        async with self.lock:
            session = self.sessions.get(device_id)
        if not session or not session.connected:
            return False
        await session.websocket.send_text(json.dumps(message, separators=(",", ":")))
        return True


hub = AndroidBridgeHub()


def install_android_bridge(app: Any) -> AndroidBridgeHub:
    @app.websocket("/v1/device/ws")
    async def android_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        session: DeviceSession | None = None
        try:
            challenge = secrets.token_urlsafe(32)
            await websocket.send_text(json.dumps({"type": "challenge", "challenge": challenge}, separators=(",", ":")))
            raw = await websocket.receive_text()
            hello = json.loads(raw)
            if hello.get("type") != "hello":
                await websocket.close(code=1008, reason="hello_required")
                return
            payload = hello.get("payload") or {}
            device_id = str(payload.get("device_id", ""))
            if not device_id or hello.get("device_id") != device_id:
                await websocket.close(code=1008, reason="invalid_device_identity")
                return
            if hello.get("challenge") != challenge:
                await websocket.close(code=1008, reason="challenge_mismatch")
                return
            if not app.state.tom_device_auth.verify_hello(device_id, hello):
                await websocket.close(code=1008, reason="authentication_failed")
                return

            session = await hub.attach(device_id, websocket)
            await websocket.send_text(json.dumps({
                "type": "hello_ack",
                "device_id": device_id,
                "sequence": 0,
                "payload": {"accepted": True, "server_capabilities": ["live_observation", "action_request", "verification"]},
            }, separators=(",", ":")))

            while True:
                raw = await websocket.receive_text()
                message = json.loads(raw)
                sequence = int(message.get("sequence", 0))
                if sequence <= session.last_sequence:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "payload": {"code": "replay_or_out_of_order", "sequence": sequence},
                    }, separators=(",", ":")))
                    continue
                if message.get("device_id") != device_id:
                    await websocket.close(code=1008, reason="device_identity_mismatch")
                    return
                session.last_sequence = sequence
                await app.state.tom_bridge_events.put(message)
        except WebSocketDisconnect:
            pass
        except (ValueError, json.JSONDecodeError):
            try:
                await websocket.close(code=1003, reason="invalid_message")
            except Exception:
                pass
        finally:
            if session:
                await hub.detach(session.device_id)

    return hub
