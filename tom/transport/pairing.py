from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PairingChallenge:
    device_id: str
    challenge: str
    expires_at: float


class PairingManager:
    """One-time enrollment primitives; persistent storage belongs to the deployment."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._challenges: dict[str, PairingChallenge] = {}
        self._secrets: dict[str, bytes] = {}

    def begin(self, device_id: str) -> PairingChallenge:
        challenge = secrets.token_urlsafe(32)
        item = PairingChallenge(device_id, challenge, time.time() + self.ttl_seconds)
        self._challenges[device_id] = item
        return item

    def enroll(self, device_id: str, challenge: str) -> str:
        item = self._challenges.get(device_id)
        if item is None or time.time() >= item.expires_at or not hmac.compare_digest(item.challenge, challenge):
            raise PermissionError("invalid or expired pairing challenge")
        secret = secrets.token_bytes(32)
        self._secrets[device_id] = secret
        self._challenges.pop(device_id, None)
        return secret.hex()

    def verify(self, device_id: str, proof: str, nonce: str) -> bool:
        secret = self._secrets.get(device_id)
        if secret is None:
            return False
        expected = hmac.new(secret, nonce.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, proof)

    def revoke(self, device_id: str) -> None:
        self._secrets.pop(device_id, None)
        self._challenges.pop(device_id, None)
