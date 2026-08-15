from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import Risk, ToolCall


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class PermissionPolicy:
    """Central capability policy. High-impact side effects never bypass explicit approval."""

    allow_low_risk: bool = True
    enabled_capabilities: set[str] = field(default_factory=set)

    def decide(self, call: ToolCall, approved: bool = False) -> Decision:
        if call.risk is Risk.CRITICAL and not approved:
            return Decision.ASK
        if call.risk is Risk.HIGH and not approved:
            return Decision.ASK
        if call.risk is Risk.READ:
            return Decision.ALLOW
        if call.risk is Risk.LOW and self.allow_low_risk:
            return Decision.ALLOW
        return Decision.DENY
