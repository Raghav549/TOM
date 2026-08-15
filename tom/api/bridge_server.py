from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from tom.device.core_receiver import CoreBridgeReceiver
from tom.live_events import LiveEventStream


@dataclass
class DeviceSession:
    device_id: str
    websocket: WebSocket
    last_sequence: int = 0
    connected: bool = True


class AndroidBridgeHub:
    """Authenticated Android WSS hub with action/verification correlation and task-event fanout."""

    def __init__(self, event_stream: LiveEventStream | None = None, core_receiver: CoreBridgeReceiver | None = None) -> None:
        self.sessions: dict[str, DeviceSession] = {}
        self.lock = asyncio.Lock()
        self._waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.event_stream = event_stream
        self.core_receiver = core_receiver

    async def emit(self, event_type: str, payload: dict[str, Any], *, task_id: str | None = None) -> None:
        if self.event_stream:
            event = await self.event_stream.publish(event_type, payload, task_id=task_id)
            target = str(payload.get("device_id") or "").strip()
            if target:
                await self.send(target, {
                    "type": "task_event",
                    "message_id": secrets.token_urlsafe(12),
                    "sequence": event.seq,
                    "device_id": target,
                    "payload": event.as_dict(),
                })

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
        await self.emit("device.connected", {"device_id": device_id}, task_id=None)
        return session

    async def detach(self, device_id: str) -> None:
        async with self.lock:
            session = self.sessions.get(device_id)
            if session:
                session.connected = False
                self.sessions.pop(device_id, None)
        await self.emit("device.disconnected", {"device_id": device_id}, task_id=None)

    async def send(self, device_id: str, message: dict[str, Any]) -> bool:
        async with self.lock:
            session = self.sessions.get(device_id)
        if not session or not session.connected:
            return False
        await session.websocket.send_text(json.dumps(message, separators=(",", ":")))
        return True

    async def request_action(self, device_id: str, task_id: str, action: str, arguments: dict[str, Any], approval_token: str | None = None, timeout: float = 45.0) -> dict[str, Any]:
        action_id = secrets.token_urlsafe(18)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        key = f"action:{action_id}"
        async with self.lock:
            self._waiters[key] = future
        await self.emit("action.requested", {"device_id": device_id, "action": action, "action_id": action_id}, task_id=task_id)
        message = {"type": "action_request", "message_id": secrets.token_urlsafe(12), "sequence": 0, "device_id": device_id, "payload": {"task_id": task_id, "action_id": action_id, "approval_token": approval_token or "", "action": action, "arguments": arguments}}
        sent = await self.send(device_id, message)
        if not sent:
            async with self.lock:
                self._waiters.pop(key, None)
            return {"accepted": False, "status": "device_not_connected", "action_id": action_id}
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            if result.get("accepted") and result.get("status") in {"completed", "verified"} and self.core_receiver:
                verified = await self.request_verification(device_id, task_id, action_id, timeout=15.0)
                if verified is None:
                    return {**result, "status": "verification_unknown", "verified": False, "action_id": action_id}
                return {**result, "status": verified["verification"]["status"], "verified": verified["verification"]["status"] == "verified", "verification": verified["verification"], "observation_id": verified.get("observation_id")}
            return result
        except asyncio.TimeoutError:
            return {"accepted": False, "status": "action_timeout", "action_id": action_id}
        finally:
            async with self.lock:
                self._waiters.pop(key, None)

    async def request_verification(self, device_id: str, task_id: str, action_id: str, timeout: float = 15.0) -> dict[str, Any] | None:
        key = f"verification:{task_id}:{action_id}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        async with self.lock:
            self._waiters[key] = future
        await self.emit("verification.started", {"device_id": device_id, "action_id": action_id}, task_id=task_id)
        await self.send(device_id, {"type": "observation_request", "message_id": secrets.token_urlsafe(12), "sequence": 0, "device_id": device_id, "payload": {"task_id": task_id, "action_id": action_id, "reason": "post_action_verification"}})
        await self.send(device_id, {"type": "screenshot_request", "message_id": secrets.token_urlsafe(12), "sequence": 0, "device_id": device_id, "payload": {"request_id": secrets.token_urlsafe(12), "task_id": task_id, "action_id": action_id, "reason": "post_action_verification"}})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            await self.emit("verification.unknown", {"device_id": device_id, "action_id": action_id}, task_id=task_id)
            return None
        finally:
            async with self.lock:
                self._waiters.pop(key, None)

    async def resolve_incoming(self, message: dict[str, Any]) -> None:
        message_type = str(message.get("type", ""))
        payload = message.get("payload") or {}
        task_id = str(payload.get("task_id") or "") or None
        if message_type == "action_result":
            action_id = str(payload.get("action_id", ""))
            key = f"action:{action_id}"
            await self.emit("action.result", payload, task_id=task_id)
        elif message_type == "observation":
            action_id = str(payload.get("action_id", ""))
            if task_id and action_id:
                await self.emit("observation.received", payload, task_id=task_id)
            key = ""
        elif message_type in {"screenshot_chunk", "screenshot_complete"}:
            await self.emit(message_type, payload, task_id=task_id)
            key = ""
        else:
            await self.emit(f"device.{message_type or 'event'}", payload, task_id=task_id)
            key = ""
        if key:
            async with self.lock:
                future = self._waiters.get(key)
            if future and not future.done():
                future.set_result(payload)

    async def resolve_verification(self, result: dict[str, Any]) -> None:
        task_id = str(result.get("task_id") or "")
        action_id = str(result.get("action_id") or "")
        if not task_id or not action_id:
            return
        status = str(result.get("verification", {}).get("status", "unknown"))
        payload = dict(result)
        payload["device_id"] = str(result.get("device_id") or "")
        await self.emit(f"verification.{status}", payload, task_id=task_id)
        key = f"verification:{task_id}:{action_id}"
        async with self.lock:
            future = self._waiters.get(key)
        if future and not future.done():
            future.set_result(result)


async def _forward_to_core(hub: AndroidBridgeHub, message: dict[str, Any]) -> None:
    if hub.core_receiver is None:
        return
    try:
        await hub.core_receiver.receive(json.dumps(message, separators=(",", ":")))
    except Exception as exc:
        task_id = str((message.get("payload") or {}).get("task_id") or "") or None
        await hub.emit("verification.error", {"error": str(exc), "device_id": message.get("device_id", "")}, task_id=task_id)


def install_android_bridge(app: Any, *, event_stream: LiveEventStream | None = None, core_receiver: CoreBridgeReceiver | None = None) -> AndroidBridgeHub:
    live_hub = AndroidBridgeHub(event_stream=event_stream, core_receiver=core_receiver)
    app.state.tom_android_hub = live_hub

    async def handler(websocket: WebSocket) -> None:
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
            if not device_id or hello.get("device_id") != device_id or hello.get("challenge") != challenge or not app.state.tom_device_auth.verify_hello(device_id, hello):
                await websocket.close(code=1008, reason="authentication_failed")
                return
            session = await live_hub.attach(device_id, websocket)
            await websocket.send_text(json.dumps({"type": "hello_ack", "device_id": device_id, "sequence": 0, "payload": {"accepted": True, "server_capabilities": ["live_observation", "action_request", "verification", "multimodal_verification", "request_correlation", "core_event_stream", "task_event_replay"]}}, separators=(",", ":")))
            while True:
                raw = await websocket.receive_text()
                message = json.loads(raw)
                sequence = int(message.get("sequence", 0))
                if sequence <= session.last_sequence:
                    await websocket.send_text(json.dumps({"type": "error", "payload": {"code": "replay_or_out_of_order", "sequence": sequence}}, separators=(",", ":")))
                    continue
                if message.get("device_id") != device_id:
                    await websocket.close(code=1008, reason="device_identity_mismatch")
                    return
                session.last_sequence = sequence
                await live_hub.resolve_incoming(message)
                await _forward_to_core(live_hub, message)
                if event_stream:
                    await event_stream.publish("android." + str(message.get("type") or "event"), message.get("payload") or {}, task_id=str((message.get("payload") or {}).get("task_id") or "") or None)
        except WebSocketDisconnect:
            pass
        except (ValueError, json.JSONDecodeError):
            try:
                await websocket.close(code=1003, reason="invalid_message")
            except RuntimeError:
                pass
        finally:
            if session:
                await live_hub.detach(session.device_id)

    app.websocket("/v1/device/ws")(handler)
    app.websocket("/v1/device/live")(handler)
    return live_hub
