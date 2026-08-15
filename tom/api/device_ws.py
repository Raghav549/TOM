from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tom.device.core_receiver import CoreBridgeReceiver

router = APIRouter(prefix="/v1/device", tags=["device"])


def build_device_websocket(perception, on_plan=None) -> APIRouter:
    """Attach the real Core multimodal receiver to an existing FastAPI app.

    Authentication/authorization remains owned by the existing device-session
    layer; this adapter only handles typed WebSocket messages and perception.
    """
    receiver = CoreBridgeReceiver(perception, on_plan=on_plan)

    @router.websocket("/ws/multimodal")
    async def multimodal_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive_text()
                try:
                    result = await receiver.receive(message)
                    if result is not None:
                        await websocket.send_json({"type": "perception_decision", "payload": result})
                except (ValueError, KeyError) as exc:
                    await websocket.send_json({"type": "error", "error": type(exc).__name__, "detail": str(exc)})
        except WebSocketDisconnect:
            return

    return router
