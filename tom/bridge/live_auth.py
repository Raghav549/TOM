from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import dataclass

from ..device_auth import DeviceAuthenticator


@dataclass(frozen=True)
class LiveAuthConfig:
    """Loads device credentials from a deployment secret, never from source."""

    secrets: dict[str, bytes]

    @classmethod
    def from_environment(cls) -> LiveAuthConfig:
        raw = os.getenv("TOM_DEVICE_SECRETS_JSON", "")
        if not raw:
            return cls({})
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise TypeError("TOM_DEVICE_SECRETS_JSON must be an object")
        secrets_by_device: dict[str, bytes] = {}
        for device_id, encoded in parsed.items():
            if not isinstance(device_id, str) or not isinstance(encoded, str):
                raise TypeError("device credentials must map strings to base64 strings")
            secret = base64.b64decode(encoded, validate=True)
            if len(secret) < 32:
                raise ValueError("device secret must contain at least 32 bytes")
            secrets_by_device[device_id] = secret
        return cls(secrets_by_device)


class LiveDeviceAuthenticator:
    def __init__(self, config: LiveAuthConfig | None = None) -> None:
        self._config = config or LiveAuthConfig.from_environment()
        self._auth = DeviceAuthenticator()
        for device_id, secret in self._config.secrets.items():
            self._auth.enroll(device_id, secret)

    def challenge_session(self, device_id: str) -> tuple[str, str] | None:
        if device_id not in self._config.secrets:
            return None
        return secrets.token_urlsafe(32), secrets.token_urlsafe(24)

    def verify(self, device_id: str, challenge: str, proof: str) -> bool:
        return self._auth.verify_hello(device_id, {"challenge": challenge, "proof": proof})
