from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tom.transport.protocol import BridgeMessage, MessageType, ReplayGuard
from tom.transport.session import DeviceSession


class TransportRouter:
    """Route bridge messages only after session and replay validation."""

    def __init__(self) -> None:
        self.sessions: dict[str, DeviceSession] = {}
        self.replay = ReplayGuard()
        self.handlers: dict[MessageType, Callable[[BridgeMessage], Any]] = {}

    def register(self, message_type: MessageType, handler: Callable[[BridgeMessage], Any]) -> None:
        self.handlers[message_type] = handler

    def receive(self, connection_id: str, message: BridgeMessage) -> Any:
        if not self.replay.accept(connection_id, message.sequence or 0):
            raise ValueError("replayed or out-of-order bridge message")
        session = self.sessions.setdefault(message.device_id, DeviceSession(message.device_id))
        if message.type is MessageType.HELLO:
            session.heartbeat()
        elif message.type is MessageType.HEARTBEAT:
            session.heartbeat()
        elif session.state.value in {"pairing", "revoked"}:
            raise PermissionError("device session is not connected")
        handler = self.handlers.get(message.type)
        if handler is None:
            return {"status": "accepted", "type": message.type.value}
        return handler(message)
