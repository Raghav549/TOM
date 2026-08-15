from __future__ import annotations

from dataclasses import dataclass
import re


SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password)\s*[:=]\s*[^\s]+"),
)


@dataclass(frozen=True)
class Redaction:
    value: str
    changed: bool


def redact(text: str) -> Redaction:
    output = text
    for pattern in SECRET_PATTERNS:
        output = pattern.sub("[REDACTED]", output)
    return Redaction(output, output != text)


def safe_log_payload(payload: dict) -> dict:
    """Shallow redaction for audit/event logs; raw credentials must never enter event payloads."""
    result = dict(payload)
    for key in tuple(result):
        if any(word in key.lower() for word in ("token", "secret", "password", "api_key")):
            result[key] = "[REDACTED]"
        elif isinstance(result[key], str):
            result[key] = redact(result[key]).value
    return result
