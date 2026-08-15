from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BridgeSession:
    device_id: str
    connected: bool = False
    last_seq: int = 0
    last_seen: float = field(default_factory=time.monotonic)

    def accept_sequence(self, sequence: int) -> bool:
        if sequence <= self.last_seq:
            return False
        self.last_seq = sequence
        self.last_seen = time.monotonic()
        return True


class AndroidBridgeRuntime:
    """Transport-neutral runtime for authenticated Android sessions.

    A WebSocket/QUIC implementation can attach send/receive functions without
    changing TOM's agent or permission layers.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, BridgeSession] = {}
        self._senders: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        device_id: str,
        sender: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> BridgeSession:
        async with self._lock:
            session = BridgeSession(device_id=device_id, connected=True)
            self._sessions[device_id] = session
            self._senders[device_id] = sender
            return session

    async def disconnect(self, device_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(device_id)
            if session:
                session.connected = False
            self._senders.pop(device_id, None)

    async def receive(self, device_id: str, envelope: dict[str, Any]) -> bool:
        session = self._sessions.get(device_id)
        if session is None or not session.connected:
            return False
        sequence = int(envelope.get("sequence", 0))
        if not session.accept_sequence(sequence):
            return False
        return True

    async def send_action(
        self,
        device_id: str,
        action: dict[str, Any],
    ) -> None:
        sender = self._senders.get(device_id)
        session = self._sessions.get(device_id)
        if sender is None or session is None or not session.connected:
            raise ConnectionError("Android device is not connected")
        await sender({"type": "action.request", "device_id": device_id, "payload": action})

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        return [
            {
                "device_id": session.device_id,
                "connected": session.connected,
                "last_sequence": session.last_seq,
                "age_seconds": round(now - session.last_seen, 3),
            }
            for session in self._sessions.values()
        ]
