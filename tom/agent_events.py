from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class AgentEventBus:
    """Small async event bus joining voice, planner, device and UI layers."""

    _handlers: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, **payload}
        handlers = [*self._handlers.get(event_type, []), *self._handlers.get("*", [])]
        if not handlers:
            return
        await asyncio.gather(*(handler(event) for handler in handlers))


@dataclass(frozen=True)
class ActionLifecycle:
    task_id: str
    action_id: str
    tool: str
    status: str
    attempt: int = 0
    output: Any = None
    error: str | None = None
