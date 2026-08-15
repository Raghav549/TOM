from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from .credentials import CredentialManager

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
STATE_TTL_SECONDS = 600
SCOPES = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)


@dataclass
class GoogleOAuth:
    credentials: CredentialManager

    def _env(self, name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise RuntimeError(f"{name} is not configured")
        return value

    def client_id(self) -> str:
        return self._env("TOM_GOOGLE_CLIENT_ID")

    def client_secret(self) -> str:
        return self._env("TOM_GOOGLE_CLIENT_SECRET")

    def redirect_uri(self) -> str:
        return self._env("TOM_GOOGLE_REDIRECT_URI")

    def _state_key(self) -> bytes:
        secret = os.getenv("TOM_CREDENTIAL_MASTER_KEY", "").strip() or self.client_secret()
        return hashlib.sha256(secret.encode("utf-8")).digest()

    def _encode_state(self, nonce: str) -> str:
        payload = {"iat": int(time.time()), "nonce": nonce}
        raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(self._state_key(), raw.encode(), hashlib.sha256).hexdigest()
        return f"{raw}.{signature}"

    def _validate_state(self, state: str) -> None:
        try:
            raw, signature = state.split(".", 1)
            expected = hmac.new(self._state_key(), raw.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())
            issued = int(payload["iat"])
            if issued > int(time.time()) + 30 or int(time.time()) - issued > STATE_TTL_SECONDS:
                raise ValueError
            if not str(payload.get("nonce", "")):
                raise ValueError
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("invalid or expired Google OAuth state") from exc

    def begin(self) -> dict[str, str]:
        state = self._encode_state(secrets.token_urlsafe(24))
        params = {
            "client_id": self.client_id(),
            "redirect_uri": self.redirect_uri(),
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return {"state": state, "authorization_url": f"{GOOGLE_AUTH}?{urlencode(params)}"}

    async def exchange(self, code: str, state: str) -> dict[str, Any]:
        self._validate_state(state)
        if not code.strip():
            raise RuntimeError("Google OAuth callback did not contain an authorization code")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                GOOGLE_TOKEN,
                data={
                    "code": code,
                    "client_id": self.client_id(),
                    "client_secret": self.client_secret(),
                    "redirect_uri": self.redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            token = response.json()
        token["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600))
        self.credentials.set("google", token)
        return {"connected": True, "token_type": token.get("token_type"), "scope": token.get("scope"), "expires_at": token["expires_at"]}

    async def access_token(self) -> str:
        token = self.credentials.get("google")
        if not token:
            raise RuntimeError("Google account is not connected; complete OAuth first")
        if int(token.get("expires_at", 0)) > int(time.time()) + 60:
            return str(token["access_token"])
        refresh_token = str(token.get("refresh_token", ""))
        if not refresh_token:
            raise RuntimeError("Google refresh token is missing; reconnect Google")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                GOOGLE_TOKEN,
                data={
                    "client_id": self.client_id(),
                    "client_secret": self.client_secret(),
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            refreshed = response.json()
        token.update(refreshed)
        token["refresh_token"] = refresh_token
        token["expires_at"] = int(time.time()) + int(refreshed.get("expires_in", 3600))
        self.credentials.set("google", token)
        return str(token["access_token"])

    def connected(self) -> bool:
        return self.credentials.configured("google")

    def status(self) -> dict[str, Any]:
        token = self.credentials.get("google")
        if not token:
            return {"connected": False, "provider": "google", "scopes": []}
        scopes = str(token.get("scope", "")).split()
        return {
            "connected": True,
            "provider": "google",
            "scopes": scopes,
            "expires_at": int(token.get("expires_at", 0)),
            "has_refresh_token": bool(token.get("refresh_token")),
        }
