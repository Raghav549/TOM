from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from .credentials import CredentialManager

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)


@dataclass
class GoogleOAuth:
    credentials: CredentialManager

    def client_id(self) -> str:
        import os

        value = os.getenv("TOM_GOOGLE_CLIENT_ID", "").strip()
        if not value:
            raise RuntimeError("TOM_GOOGLE_CLIENT_ID is not configured")
        return value

    def client_secret(self) -> str:
        import os

        value = os.getenv("TOM_GOOGLE_CLIENT_SECRET", "").strip()
        if not value:
            raise RuntimeError("TOM_GOOGLE_CLIENT_SECRET is not configured")
        return value

    def redirect_uri(self) -> str:
        import os

        value = os.getenv("TOM_GOOGLE_REDIRECT_URI", "").strip()
        if not value:
            raise RuntimeError("TOM_GOOGLE_REDIRECT_URI is not configured")
        return value

    def authorization_url(self, state: str) -> str:
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
        return f"{GOOGLE_AUTH}?{urlencode(params)}"

    async def exchange(self, code: str) -> dict[str, Any]:
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
        return token

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
