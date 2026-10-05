"""Authentication for operator WebSockets, separate from paired-device HMAC."""
from __future__ import annotations

import hmac
import os

from fastapi import WebSocket


async def authorize_operator_socket(websocket: WebSocket) -> bool:
    expected = os.getenv("TOM_API_TOKEN", "").strip()
    production = os.getenv("TOM_ENV", "development").lower() == "production"
    if not expected and not production:
        return True
    supplied = websocket.headers.get("authorization", "")
    if expected and hmac.compare_digest(supplied, f"Bearer {expected}"):
        return True
    # Reject before accept: browsers must use an authenticated same-origin proxy;
    # never place long-lived API credentials in a WebSocket URL/query string.
    await websocket.close(code=1008)
    return False
