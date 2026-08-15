from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field


@dataclass
class DeviceAuthenticator:
    """Small trust anchor for the live bridge.

    Device enrollment should provision the secret out-of-band. The WebSocket
    handshake carries only a proof derived from that secret; the raw secret is
    never transmitted.
    """

    _secrets: dict[str, bytes] = field(default_factory=dict)
    _revoked: set[str] = field(default_factory=set)

    def enroll(self, device_id: str, secret: bytes | None = None) -> bytes:
        if not device_id:
            raise ValueError("device_id is required")
        value = secret or os.urandom(32)
        self._secrets[device_id] = value
        self._revoked.discard(device_id)
        return value

    def revoke(self, device_id: str) -> None:
        self._revoked.add(device_id)

    def verify_hello(self, device_id: str, hello: dict) -> bool:
        if device_id in self._revoked:
            return False
        secret = self._secrets.get(device_id)
        if secret is None:
            return False
        proof = str(hello.get("proof", ""))
        challenge = str(hello.get("challenge", ""))
        if not proof or not challenge:
            return False
        expected = hmac.new(secret, challenge.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, proof)
