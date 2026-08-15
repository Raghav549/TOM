from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventBus:
    """In-process event stream used by the API/client layer; replaceable by Redis/NATS."""

    _subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)

    async def publish(self, event_type: str, **data: Any) -> None:
        event = {"type": event_type, "data": data}
        for queue in tuple(self._subscribers):
            await queue.put(event)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
