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
    """Central capability policy.

    High-impact side effects require explicit approval. An approved call is
    allowed only for the exact tool invocation presented to the policy.
    """

    allow_low_risk: bool = True
    enabled_capabilities: set[str] = field(default_factory=set)

    def decide(self, call: ToolCall, approved: bool = False) -> Decision:
        if approved and call.risk in {Risk.HIGH, Risk.CRITICAL}:
            return Decision.ALLOW
        if call.risk in {Risk.HIGH, Risk.CRITICAL}:
            return Decision.ASK
        if call.risk is Risk.READ:
            return Decision.ALLOW
        if call.risk is Risk.LOW and self.allow_low_risk:
            return Decision.ALLOW
        return Decision.DENY
