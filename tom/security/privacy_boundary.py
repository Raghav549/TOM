from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ExposureDecision(str, Enum):
    LOCAL_ONLY = "local_only"
    ALLOW = "allow"
    MASK = "mask"
    DENY = "deny"


@dataclass(frozen=True)
class ExposurePolicy:
    """Decides whether an observation may cross the device/core boundary.

    This is deliberately conservative. The phone-side implementation should
    apply the same policy before sending screenshots or UI text to a remote
    model. It is not a replacement for Android's own permission/security model.
    """

    sensitive_markers: tuple[str, ...] = (
        "password", "passcode", "otp", "one-time password", "cvv",
        "credit card", "debit card", "bank account", "upi pin",
        "private key", "seed phrase", "recovery phrase",
    )

    def classify_text(self, text: str) -> ExposureDecision:
        normalized = text.casefold()
        if any(marker in normalized for marker in self.sensitive_markers):
            return ExposureDecision.MASK
        return ExposureDecision.ALLOW

    def classify_fields(self, fields: Iterable[str]) -> dict[str, ExposureDecision]:
        return {field: self.classify_text(field) for field in fields}
