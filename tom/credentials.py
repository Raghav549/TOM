from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class CredentialManager:
    """Small encrypted credential vault for provider tokens.

    A master secret is supplied by TOM_CREDENTIAL_MASTER_KEY. Credentials are
    never committed to the repository. If the master key is absent, reads may
    still resolve directly from provider-specific environment variables, but
    persistent writes are rejected.
    """

    def __init__(self, data_dir: Path):
        self.path = data_dir / "credentials.enc"
        self._lock = RLock()
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _fernet() -> Fernet | None:
        secret = os.getenv("TOM_CREDENTIAL_MASTER_KEY", "").strip()
        if not secret:
            return None
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _load(self) -> None:
        if self._cache or not self.path.exists():
            return
        fernet = self._fernet()
        if fernet is None:
            return
        try:
            raw = fernet.decrypt(self.path.read_bytes())
            self._cache = json.loads(raw.decode("utf-8"))
        except (InvalidToken, ValueError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("credential vault cannot be decrypted") from exc

    def get(self, provider: str) -> dict[str, Any] | None:
        with self._lock:
            self._load()
            value = self._cache.get(provider)
            return dict(value) if value else None

    def set(self, provider: str, credentials: dict[str, Any]) -> None:
        with self._lock:
            fernet = self._fernet()
            if fernet is None:
                raise RuntimeError("TOM_CREDENTIAL_MASTER_KEY is required for credential storage")
            self._load()
            self._cache[provider] = dict(credentials)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._cache, separators=(",", ":"), sort_keys=True).encode("utf-8")
            temp = self.path.with_suffix(".tmp")
            temp.write_bytes(fernet.encrypt(payload))
            temp.replace(self.path)

    def delete(self, provider: str) -> None:
        with self._lock:
            self._load()
            self._cache.pop(provider, None)
            if not self._cache:
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                return
            fernet = self._fernet()
            if fernet is None:
                raise RuntimeError("TOM_CREDENTIAL_MASTER_KEY is required for credential storage")
            payload = json.dumps(self._cache, separators=(",", ":"), sort_keys=True).encode("utf-8")
            self.path.write_bytes(fernet.encrypt(payload))

    def configured(self, provider: str) -> bool:
        return self.get(provider) is not None

    def status(self, providers: list[str]) -> dict[str, bool]:
        return {provider: self.configured(provider) for provider in providers}


def env_credential(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None
