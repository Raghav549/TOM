from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field


@dataclass
class DeviceAuthenticator:
    """Trust anchor for the live bridge.

    Device enrollment is provisioned out-of-band through TOM_DEVICE_SECRETS_JSON.
    The WebSocket handshake carries only an HMAC proof; the raw secret is never
    transmitted or logged.
    """

    _secrets: dict[str, bytes] = field(default_factory=dict)
    _revoked: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        raw = os.getenv("TOM_DEVICE_SECRETS_JSON", "").strip()
        if not raw:
            return
        try:
            values = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("TOM_DEVICE_SECRETS_JSON must contain valid JSON") from exc
        if not isinstance(values, dict):
            raise TypeError("TOM_DEVICE_SECRETS_JSON must be an object mapping device IDs to secrets")
        for device_id, encoded in values.items():
            if not isinstance(device_id, str) or not isinstance(encoded, str) or not encoded:
                raise ValueError("device secrets must map non-empty device IDs to non-empty strings")
            try:
                secret = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                secret = encoded.encode("utf-8")
            if len(secret) < 32:
                raise ValueError(f"device secret for {device_id!r} must be at least 32 bytes")
            self._secrets[device_id] = secret

    def enroll(self, device_id: str, secret: bytes | None = None) -> bytes:
        if not device_id:
            raise ValueError("device_id is required")
        value = secret or os.urandom(32)
        if len(value) < 32:
            raise ValueError("device secret must be at least 32 bytes")
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
