from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class GuardedContext:
    text: str
    source: str
    trusted: bool = False


_INSTRUCTION_PATTERNS = (
    re.compile(r"ignore (?:all|any|previous|prior) instructions", re.I),
    re.compile(r"system message", re.I),
    re.compile(r"developer message", re.I),
    re.compile(r"reveal (?:your|the) (?:system|developer) prompt", re.I),
)


def guard_environment_text(text: str, source: str) -> GuardedContext:
    """Mark environment-derived text as untrusted; never promote it to agent policy."""
    # This is deliberately not a prompt-injection 'filter'. Detection is advisory.
    # The architectural guarantee is that returned context is never trusted policy.
    return GuardedContext(text=text, source=source, trusted=False)


def contains_instruction_like_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INSTRUCTION_PATTERNS)
