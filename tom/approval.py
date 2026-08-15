from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Risk, ToolCall


@dataclass
class ApprovalGate:
    required: bool = True
    approved: set[str] = field(default_factory=set)

    def token_for(self, call: ToolCall) -> str:
        return f"{call.name}:{hash(repr(sorted(call.arguments.items())))}"

    def needs_approval(self, call: ToolCall) -> bool:
        if not self.required:
            return False
        return call.risk in {Risk.HIGH, Risk.CRITICAL}

    def approve(self, call: ToolCall) -> str:
        token = self.token_for(call)
        self.approved.add(token)
        return token

    def consume(self, call: ToolCall) -> bool:
        token = self.token_for(call)
        if token in self.approved:
            self.approved.remove(token)
            return True
        return False
