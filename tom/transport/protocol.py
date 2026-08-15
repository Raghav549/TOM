from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    HELLO = "hello"
    CAPABILITIES = "capabilities"
    OBSERVATION = "observation"
    ACTION = "action"
    ACTION_RESULT = "action_result"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


@dataclass(frozen=True)
class BridgeMessage:
    id: str
    type: MessageType
    timestamp_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    sequence: int | None = None


class ReplayGuard:
    """Reject duplicate/out-of-order sequence numbers per connection."""

    def __init__(self) -> None:
        self._last: dict[str, int] = {}

    def accept(self, connection_id: str, sequence: int) -> bool:
        previous = self._last.get(connection_id, -1)
        if sequence <= previous:
            return False
        self._last[connection_id] = sequence
        return True
