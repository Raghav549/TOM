from __future__ import annotations

import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .live_auth import LiveDeviceAuthenticator
from .live_protocol import BridgeEnvelope
from .live_router import LiveBridgeRouter

router = APIRouter()
live_router = LiveBridgeRouter()
_live_auth = LiveDeviceAuthenticator()


@router.websocket("/v1/device/live")
async def android_live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    authenticated = False
    device_id: str | None = None
    session_id: str | None = None
    challenge: str | None = None
    challenge_session: str | None = None
    server_sequence = 0
    try:
        # Bootstrap is intentionally unauthenticated only for the challenge.
        # No action or observation is accepted until the proof is verified.
        while not authenticated:
            raw = await websocket.receive_text()
            try:
                envelope = BridgeEnvelope.decode(raw)
            except (ValueError, TypeError):
                await websocket.send_json({"type": "ERROR", "code": "INVALID_ENVELOPE"})
                continue
            if envelope.type != "HELLO":
                await websocket.send_json({"type": "ERROR", "code": "AUTH_REQUIRED"})
                continue

            candidate = envelope.device_id
            issued = _live_auth.challenge_session(candidate)
            if issued is None:
                await websocket.send_json({"type": "ERROR", "code": "UNKNOWN_DEVICE"})
                await websocket.close(code=4401)
                return

            # First HELLO requests a challenge; second HELLO carries proof.
            proof = str(envelope.payload.get("proof", ""))
            requested_challenge = str(envelope.payload.get("challenge", ""))
            if not challenge:
                challenge, challenge_session = issued
                await websocket.send_json({
                    "type": "CHALLENGE",
                    "challenge": challenge,
                    "session_id": challenge_session,
                    "protocol": 1,
                })
                continue

            if requested_challenge != challenge or envelope.session_id != challenge_session:
                await websocket.send_json({"type": "ERROR", "code": "CHALLENGE_MISMATCH"})
                await websocket.close(code=4401)
                return
            if not _live_auth.verify(candidate, challenge, proof):
                await websocket.send_json({"type": "ERROR", "code": "AUTH_FAILED"})
                await websocket.close(code=4401)
                return

            device_id = candidate
            session_id = challenge_session
            authenticated = True
            server_sequence += 1
            await websocket.send_text(BridgeEnvelope(
                "HELLO_ACK", device_id, session_id, server_sequence, None,
                {"protocol": 1, "authenticated": True}
            ).encode())

        while True:
            raw = await websocket.receive_text()
            try:
                envelope = BridgeEnvelope.decode(raw)
            except (ValueError, TypeError):
                await websocket.send_json({"type": "ERROR", "code": "INVALID_ENVELOPE"})
                continue

            if envelope.device_id != device_id or envelope.session_id != session_id:
                await websocket.send_json({"type": "ERROR", "code": "SESSION_MISMATCH"})
                continue

            event = live_router.handle(envelope)
            if event is not None:
                await websocket.send_json({"type": "ROUTED", "event": event["event"], "data": event})
    except WebSocketDisconnect:
        return
