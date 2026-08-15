from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from tom.transport.protocol import BridgeMessage, MessageType
from tom.transport.router import TransportRouter


async def serve_device_websocket(
    websocket: WebSocket,
    router: TransportRouter,
    on_message: Callable[[BridgeMessage], Awaitable[Any] | Any] | None = None,
) -> None:
    """Serve a single authenticated transport connection.

    TLS/authentication are expected at the deployment boundary. The message
    router still enforces device/session and replay rules independently.
    """
    await websocket.accept()
    connection_id = f"ws:{id(websocket)}"
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            message = BridgeMessage(
                id=str(data["id"]),
                type=MessageType(data["type"]),
                timestamp_ms=int(data["timestamp_ms"]),
                payload=dict(data.get("payload", {})),
                correlation_id=data.get("correlation_id"),
                sequence=int(data["sequence"]),
            )
            result = router.receive(connection_id, message)
            if on_message is not None:
                callback_result = on_message(message)
                if hasattr(callback_result, "__await__"):
                    result = await callback_result
            await websocket.send_json({
                "type": "ack",
                "message_id": message.id,
                "sequence": message.sequence,
                "result": result,
            })
    except WebSocketDisconnect:
        return
