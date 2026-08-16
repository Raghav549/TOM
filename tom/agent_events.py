import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class AgentEventBus:
    """Async runtime event bus with a single live UI/voice sink."""

    _handlers: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return
        if not handlers:
            self._handlers.pop(event_type, None)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, **payload}
        handlers = [*self._handlers.get(event_type, []), *self._handlers.get("*", [])]
        if handlers:
            await asyncio.gather(*(handler(event) for handler in handlers))
        # The FastAPI application installs its LiveEventStream as the default
        # sink before accepting requests. Keeping this forwarding here means
        # planner/device/voice events cannot silently bypass the live UI.
        from .live_events import LiveEventStream

        stream = LiveEventStream.default()
        if stream is not None:
            task_id = payload.get("task_id")
            live_payload = {key: value for key, value in payload.items() if key != "task_id"}
            await stream.publish(event_type, live_payload, task_id=str(task_id) if task_id else None)


@dataclass(frozen=True)
class ActionLifecycle:
    task_id: str
    action_id: str
    tool: str
    status: str
    attempt: int = 0
    output: Any = None
    error: str | None = None
