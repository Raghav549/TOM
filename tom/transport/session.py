from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum


class SessionState(str, Enum):
    PAIRING = "pairing"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    REVOKED = "revoked"


@dataclass
class DeviceSession:
    device_id: str
    state: SessionState = SessionState.PAIRING
    last_sequence: int = 0
    last_heartbeat: float = 0.0
    challenge: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    _secret_digest: str | None = field(default=None, repr=False)

    def provision_secret(self) -> str:
        """Create a one-time provisioning secret; only its digest is retained."""
        secret = secrets.token_urlsafe(48)
        self._secret_digest = hashlib.sha256(secret.encode()).hexdigest()
        return secret

    def authenticate(self, secret: str) -> bool:
        if self.state is SessionState.REVOKED or not self._secret_digest:
            return False
        digest = hashlib.sha256(secret.encode()).hexdigest()
        if not secrets.compare_digest(digest, self._secret_digest):
            return False
        self.state = SessionState.CONNECTED
        self.last_heartbeat = time.monotonic()
        return True

    def accept_sequence(self, sequence: int) -> bool:
        if self.state is SessionState.REVOKED or sequence <= self.last_sequence:
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
        self._secret_digest = None
