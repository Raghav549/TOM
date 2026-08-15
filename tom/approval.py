from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json

from .models import Risk, ToolCall


@dataclass
class ApprovalGate:
    required: bool = True
    approved: set[str] = field(default_factory=set)

    def token_for(self, call: ToolCall) -> str:
        payload = json.dumps(call.arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(f"{call.name}:{call.risk.value}:{payload}".encode()).hexdigest()

    def needs_approval(self, call: ToolCall) -> bool:
        return self.required and call.risk in {Risk.HIGH, Risk.CRITICAL}

    def approve(self, call: ToolCall) -> str:
        token = self.token_for(call)
        self.approved.add(token)
        return token

    def consume(self, call: ToolCall) -> bool:
        token = self.token_for(call)
        if token not in self.approved:
            return False
        self.approved.remove(token)
        return True
