from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any


class DeviceSessionState(str, Enum):
    DISCONNECTED = "disconnected"
    PAIRING = "pairing"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    REVOKED = "revoked"


@dataclass
class DeviceSession:
    device_id: str
    state: DeviceSessionState = DeviceSessionState.DISCONNECTED
    capabilities: dict[str, Any] = field(default_factory=dict)
    last_heartbeat: float = 0.0
    protocol_version: int = 1

    def connect(self, capabilities: dict[str, Any], protocol_version: int = 1) -> None:
        if self.state is DeviceSessionState.REVOKED:
            raise PermissionError("device session has been revoked")
        self.capabilities = capabilities
        self.protocol_version = protocol_version
        self.state = DeviceSessionState.CONNECTED
        self.last_heartbeat = monotonic()

    def heartbeat(self) -> None:
        if self.state is not DeviceSessionState.CONNECTED:
            return
        self.last_heartbeat = monotonic()

    def healthy(self, timeout_seconds: float = 30.0) -> bool:
        return self.state is DeviceSessionState.CONNECTED and monotonic() - self.last_heartbeat <= timeout_seconds

    def revoke(self) -> None:
        self.state = DeviceSessionState.REVOKED
        self.capabilities.clear()
