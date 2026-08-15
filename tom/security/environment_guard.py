from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentText:
    text: str
    source: str
    trusted: bool = False


@dataclass(frozen=True)
class GuardDecision:
    allow_as_data: bool
    instruction_like: bool
    reason: str


_INSTRUCTION_PATTERNS = (
    r"ignore (?:all|any|previous|prior) instructions",
    r"system prompt",
    r"developer message",
    r"reveal (?:the )?(?:password|secret|token|api key)",
    r"send (?:this|the) (?:message|email)",
    r"transfer (?:money|funds)",
    r"disable (?:security|authentication)",
)


class EnvironmentGuard:
    """Treat observed UI/notification text as untrusted data, never authority."""

    def inspect(self, item: EnvironmentText) -> GuardDecision:
        normalized = item.text.strip().lower()
        instruction_like = any(re.search(pattern, normalized) for pattern in _INSTRUCTION_PATTERNS)
        if item.trusted:
            return GuardDecision(True, instruction_like, "trusted source")
        if instruction_like:
            return GuardDecision(True, True, "untrusted environment text may contain instructions; keep as data")
        return GuardDecision(True, False, "untrusted environment text")

    def can_override_user_goal(self, item: EnvironmentText) -> bool:
        return False
