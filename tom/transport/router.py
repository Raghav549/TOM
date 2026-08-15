from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tom.transport.protocol import BridgeMessage, MessageType, ReplayGuard
from tom.transport.session import DeviceSession, SessionState


class TransportRouter:
    """Route bridge messages only after session and replay validation."""

    def __init__(self) -> None:
        self.sessions: dict[str, DeviceSession] = {}
        self.replay = ReplayGuard()
        self.handlers: dict[MessageType, Callable[[BridgeMessage], Any]] = {}

    def register(self, message_type: MessageType, handler: Callable[[BridgeMessage], Any]) -> None:
        self.handlers[message_type] = handler

    def receive(self, connection_id: str, message: BridgeMessage) -> Any:
        if message.sequence is None or not self.replay.accept(connection_id, message.sequence):
            raise ValueError("replayed or out-of-order bridge message")

        device_id = str(message.payload.get("device_id", "")).strip()
        if not device_id:
            raise ValueError("bridge message missing device_id")

        session = self.sessions.setdefault(device_id, DeviceSession(device_id))
        if message.type in {MessageType.HELLO, MessageType.HEARTBEAT}:
            session.heartbeat()
        elif session.state in {SessionState.PAIRING, SessionState.REVOKED}:
            raise PermissionError("device session is not connected")

        handler = self.handlers.get(message.type)
        if handler is None:
            return {"status": "accepted", "type": message.type.value}
        return handler(message)

    def revoke(self, device_id: str) -> None:
        session = self.sessions.get(device_id)
        if session:
            session.revoke()
