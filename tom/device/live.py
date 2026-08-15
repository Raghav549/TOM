from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tom.models import Risk, ToolCall


@dataclass
class DeviceSession:
    device_id: str
    websocket: WebSocket
    authenticated: bool = False
    pending: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def send(self, message_type: str, payload: dict[str, Any]) -> None:
        await self.websocket.send_json({
            "type": message_type,
            "message_id": secrets.token_hex(16),
            "device_id": self.device_id,
            "payload": payload,
        })

    async def request_action(self, task_id: str, action: ToolCall, approval_token: str | None = None) -> dict[str, Any]:
        action_id = secrets.token_hex(16)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[action_id] = future
        payload = {
            "task_id": task_id,
            "action_id": action_id,
            "action": action.name.removeprefix("device_"),
            "arguments": dict(action.arguments),
        }
        if approval_token:
            payload["approval_token"] = approval_token
        await self.send("action_request", payload)
        try:
            return await asyncio.wait_for(future, timeout=45.0)
        finally:
            self.pending.pop(action_id, None)


class RemoteDeviceTool:
    """Runtime Tool adapter that blocks until the real Android device reports execution."""

    def __init__(self, name: str, risk: Risk, sessions: "LiveDeviceRegistry") -> None:
        self.name = name
        self.risk = risk
        self.description = f"Execute {name} on the connected Android device and wait for verification."
        self.sessions = sessions

    async def run(self, arguments: dict[str, Any]) -> Any:
        args = dict(arguments)
        device_id = str(args.pop("device_id", "")).strip()
        task_id = str(args.pop("task_id", "")).strip()
        approval_token = args.pop("approval_token", None)
        if not device_id or not task_id:
            raise RuntimeError("device_id and task_id are required")
        session = self.sessions.get(device_id)
        if session is None or not session.authenticated:
            raise RuntimeError("Android device is not connected")
        call = ToolCall(name=self.name, arguments=args, risk=self.risk)
        result = await session.request_action(task_id, call, approval_token)
        if not result.get("accepted") or result.get("status") not in {"completed", "verified"}:
            raise RuntimeError(result.get("error") or result.get("status") or "Android action failed")
        return result


class LiveDeviceRegistry:
    def __init__(self) -> None:
        self.sessions: dict[str, DeviceSession] = {}

    def get(self, device_id: str) -> DeviceSession | None:
        return self.sessions.get(device_id)

    def register_tools(self, tools) -> None:
        actions = {
            "device_search_google": Risk.LOW,
            "device_open_url": Risk.LOW,
            "device_open_app": Risk.LOW,
            "device_back": Risk.LOW,
            "device_home": Risk.LOW,
            "device_recents": Risk.LOW,
            "device_tap": Risk.LOW,
            "device_tap_node": Risk.LOW,
            "device_long_press": Risk.LOW,
            "device_swipe": Risk.LOW,
            "device_set_text": Risk.LOW,
            "device_select": Risk.LOW,
            "device_focus": Risk.LOW,
            "device_scroll": Risk.LOW,
            "device_maps_search": Risk.LOW,
            "device_compose_email": Risk.HIGH,
            "device_compose_sms": Risk.HIGH,
            "device_upi_payment": Risk.CRITICAL,
            "device_create_calendar_event": Risk.HIGH,
        }
        for name, risk in actions.items():
            if name not in tools.tools:
                tools.register(RemoteDeviceTool(name, risk, self))

    async def handle(self, websocket: WebSocket) -> None:
        challenge = secrets.token_urlsafe(32)
        await websocket.send_json({"type": "challenge", "challenge": challenge})
        hello = json.loads(await websocket.receive_text())
        if hello.get("type") != "hello":
            await websocket.close(code=1008, reason="hello required")
            return
        device_id = str(hello.get("device_id") or (hello.get("payload") or {}).get("device_id") or "").strip()
        proof = str(hello.get("proof") or "")
        secret = _secret_for(device_id)
        expected = hmac.new(secret, challenge.encode(), hashlib.sha256).hexdigest() if secret else ""
        if not device_id or not secret or not hmac.compare_digest(proof, expected):
            await websocket.close(code=1008, reason="device authentication failed")
            return
        session = DeviceSession(device_id, websocket, authenticated=True)
        old = self.sessions.get(device_id)
        if old:
            await old.websocket.close(code=4000, reason="replaced by newer session")
        self.sessions[device_id] = session
        await session.send("authenticated", {"capabilities": (hello.get("payload") or {}).get("capabilities", [])})
        try:
            while True:
                raw = await websocket.receive()
                if raw.get("type") == "websocket.disconnect":
                    break
                if raw.get("text") is None:
                    continue
                envelope = json.loads(raw["text"])
                event_type = envelope.get("type", "")
                payload = envelope.get("payload") or envelope
                if event_type == "action_result":
                    action_id = str(payload.get("action_id", ""))
                    future = session.pending.get(action_id)
                    if future and not future.done():
                        future.set_result(payload)
                elif event_type == "observation":
                    observation = payload.get("snapshot") or payload
                    observation_id = str(payload.get("observation_id") or observation.get("timestamp_ms") or secrets.token_hex(8))
                    session.observations[observation_id] = observation
                elif event_type == "screenshot_complete":
                    pass
        except (WebSocketDisconnect, json.JSONDecodeError):
            pass
        finally:
            if self.sessions.get(device_id) is session:
                self.sessions.pop(device_id, None)


def _secret_for(device_id: str) -> bytes | None:
    import os

    raw = os.getenv(f"TOM_DEVICE_SECRET_{device_id}") or os.getenv("TOM_DEVICE_SHARED_SECRET")
    if not raw:
        return None
    return raw.encode("utf-8")


def build_live_device_router(registry: LiveDeviceRegistry) -> APIRouter:
    router = APIRouter(prefix="/v1/device", tags=["device-live"])

    @router.websocket("/live")
    async def live_device(websocket: WebSocket) -> None:
        await websocket.accept()
        await registry.handle(websocket)

    return router
