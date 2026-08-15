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
    """Authenticated live Android sessions plus request/response correlation."""

    def __init__(self) -> None:
        self.sessions: dict[str, DeviceSession] = {}
        self.lock = asyncio.Lock()
        self._waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}

    async def attach(self, device_id: str, websocket: WebSocket) -> DeviceSession:
        async with self.lock:
            old = self.sessions.get(device_id)
            if old:
                old.connected = False
                try:
                    await old.websocket.close(code=4001, reason="replaced")
                except RuntimeError:
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

    async def request_action(
        self,
        device_id: str,
        task_id: str,
        action: str,
        arguments: dict[str, Any],
        approval_token: str | None = None,
        timeout: float = 45.0,
    ) -> dict[str, Any]:
        action_id = secrets.token_urlsafe(18)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        key = f"action:{action_id}"
        async with self.lock:
            self._waiters[key] = future

        message = {
            "type": "action_request",
            "message_id": secrets.token_urlsafe(12),
            "sequence": 0,
            "device_id": device_id,
            "payload": {
                "task_id": task_id,
                "action_id": action_id,
                "approval_token": approval_token or "",
                "action": action,
                "arguments": arguments,
            },
        }
        sent = await self.send(device_id, message)
        if not sent:
            async with self.lock:
                self._waiters.pop(key, None)
            return {"accepted": False, "status": "device_not_connected", "action_id": action_id}

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"accepted": False, "status": "action_timeout", "action_id": action_id}
        finally:
            async with self.lock:
                self._waiters.pop(key, None)

    async def request_observation(self, device_id: str, task_id: str, action_id: str, timeout: float = 8.0) -> dict[str, Any] | None:
        loop = asyncio.get_running_loop()
        key = f"observation:{task_id}:{action_id}"
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        async with self.lock:
            self._waiters[key] = future
        await self.send(device_id, {
            "type": "observation_request",
            "message_id": secrets.token_urlsafe(12),
            "sequence": 0,
            "device_id": device_id,
            "payload": {"task_id": task_id, "action_id": action_id},
        })
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            async with self.lock:
                self._waiters.pop(key, None)

    async def resolve_incoming(self, message: dict[str, Any]) -> None:
        message_type = str(message.get("type", ""))
        payload = message.get("payload") or {}
        if message_type == "action_result":
            action_id = str(payload.get("action_id", ""))
            key = f"action:{action_id}"
        elif message_type == "observation":
            task_id = str(payload.get("task_id", ""))
            action_id = str(payload.get("action_id", ""))
            if not task_id or not action_id:
                return
            key = f"observation:{task_id}:{action_id}"
        else:
            return

        async with self.lock:
            future = self._waiters.get(key)
        if future and not future.done():
            future.set_result(payload)


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
                "payload": {"accepted": True, "server_capabilities": ["live_observation", "action_request", "verification", "request_correlation"]},
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
                await hub.resolve_incoming(message)
                await app.state.tom_bridge_events.put(message)
        except WebSocketDisconnect:
            pass
        except (ValueError, json.JSONDecodeError):
            try:
                await websocket.close(code=1003, reason="invalid_message")
            except RuntimeError:
                pass
        finally:
            if session:
                await hub.detach(session.device_id)

    return hub
