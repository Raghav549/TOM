from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .live_protocol import BridgeEnvelope
from .live_router import LiveBridgeRouter

router = APIRouter()
live_router = LiveBridgeRouter()


@router.websocket("/v1/device/live")
async def android_live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    authenticated = False
    device_id: str | None = None
    session_id: str | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                envelope = BridgeEnvelope.decode(raw)
            except (ValueError, TypeError):
                await websocket.send_json({"type": "ERROR", "code": "INVALID_ENVELOPE"})
                continue

            # Authentication/session validation must be supplied by the existing
            # production session layer before enabling action dispatch.
            if envelope.type == "HELLO":
                device_id = envelope.device_id
                session_id = envelope.session_id
                authenticated = True
                await websocket.send_text(BridgeEnvelope(
                    "HELLO_ACK", device_id, session_id, envelope.sequence + 1, None,
                    {"protocol": 1, "authenticated": True}
                ).encode())
                continue

            if not authenticated or envelope.device_id != device_id or envelope.session_id != session_id:
                await websocket.send_json({"type": "ERROR", "code": "SESSION_REQUIRED"})
                continue

            event = live_router.handle(envelope)
            if event is not None:
                await websocket.send_json({"type": "ROUTED", "event": event["event"], "data": event})
    except WebSocketDisconnect:
        return
