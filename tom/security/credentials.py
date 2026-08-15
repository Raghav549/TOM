from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class CredentialFingerprint:
    """Non-secret identifier useful for logs and device/session correlation."""

    value: str


def fingerprint(secret: str, *, namespace: str = "tom") -> CredentialFingerprint:
    """Create a stable, non-reversible fingerprint without logging the secret."""
    if not secret:
        return CredentialFingerprint("")
    digest = hmac.new(namespace.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()
    return CredentialFingerprint(digest[:24])


def generate_token(nbytes: int = 32) -> str:
    """Generate a high-entropy token for enrollment or internal credentials."""
    if nbytes < 16:
        raise ValueError("nbytes must be at least 16")
    return secrets.token_urlsafe(nbytes)
