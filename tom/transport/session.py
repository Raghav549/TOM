from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


class SessionState(str, Enum):
    PAIRING = "pairing"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    REVOKED = "revoked"
    CLOSED = "closed"


@dataclass
class DeviceSession:
    device_id: str
    state: SessionState = SessionState.PAIRING
    last_sequence: int = 0
    last_heartbeat: float = 0.0

    def accept_sequence(self, sequence: int) -> bool:
        if self.state is SessionState.REVOKED:
            return False
        if sequence <= self.last_sequence:
            return False
        self.last_sequence = sequence
        return True

    def heartbeat(self) -> None:
        if self.state is not SessionState.REVOKED:
            self.last_heartbeat = time.monotonic()
            self.state = SessionState.CONNECTED

    def health(self, timeout: float = 15.0) -> SessionState:
        if self.state is SessionState.REVOKED:
            return self.state
        if not self.last_heartbeat:
            return self.state
        if time.monotonic() - self.last_heartbeat > timeout:
            self.state = SessionState.DEGRADED
        return self.state

    def revoke(self) -> None:
        self.state = SessionState.REVOKED
