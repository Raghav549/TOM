from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    sequence: int
    kind: str
    payload: dict[str, Any]


class EventStream:
    """Small bounded replay buffer for reconnecting clients."""

    def __init__(self, max_events: int = 512) -> None:
        self._events: deque[StreamEvent] = deque(maxlen=max_events)
        self._sequence = 0
        self._lock = Lock()

    def publish(self, kind: str, payload: dict[str, Any]) -> StreamEvent:
        with self._lock:
            self._sequence += 1
            event = StreamEvent(self._sequence, kind, payload)
            self._events.append(event)
            return event

    def since(self, sequence: int) -> list[StreamEvent]:
        with self._lock:
            return [event for event in self._events if event.sequence > sequence]

    @property
    def latest_sequence(self) -> int:
        with self._lock:
            return self._sequence
