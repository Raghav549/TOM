from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardedContext:
    text: str
    source: str
    trusted: bool = False


_INSTRUCTION_PATTERNS = (
    re.compile(r"ignore (?:all|any|previous|prior) instructions", re.IGNORECASE),
    re.compile(r"system message", re.IGNORECASE),
    re.compile(r"developer message", re.IGNORECASE),
    re.compile(r"reveal (?:your|the) (?:system|developer) prompt", re.IGNORECASE),
)


def guard_environment_text(text: str, source: str) -> GuardedContext:
    """Mark environment-derived text as untrusted; never promote it to agent policy."""
    # This is deliberately not a prompt-injection 'filter'. Detection is advisory.
    # The architectural guarantee is that returned context is never trusted policy.
    return GuardedContext(text=text, source=source, trusted=False)


def contains_instruction_like_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INSTRUCTION_PATTERNS)
