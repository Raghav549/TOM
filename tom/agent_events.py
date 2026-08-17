from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .task_persistence import DurableTaskPersistence

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class AgentEventBus:
    """Async runtime event bus with durable transition and live UI sinks."""

    _handlers: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))
    persistence: DurableTaskPersistence = field(default_factory=DurableTaskPersistence.from_environment)
    _sequence: dict[str, int] = field(default_factory=dict)
    _recovery_report: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Runtime is constructed after FastAPI's app object exists. Register a
        # small authenticated-by-deployment recovery endpoint without coupling
        # AgentEventBus to the application module at import time.
        self._recovery_report = self.persistence.startup_recovery()
        module = sys.modules.get("tom.api.app")
        application = getattr(module, "app", None) if module else None
        if application is not None and not getattr(application.state, "tom_recovery_route_installed", False):
            @application.get("/v1/recovery/startup")
            async def startup_recovery() -> dict[str, Any]:
                return self.persistence.startup_recovery()
            application.state.tom_recovery_route_installed = True
            application.state.tom_task_persistence = self.persistence

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

        task_id = str(payload.get("task_id") or "")
        if task_id:
            sequence = self._sequence.get(task_id, 0) + 1
            self._sequence[task_id] = sequence
            action_id = str(payload.get("action_id") or "") or None
            await self.persistence.event(task_id, sequence, event_type, payload, action_id=action_id)
            if event_type == "TASK_STARTED":
                await self.persistence.start_task(
                    task_id=task_id,
                    conversation_id=task_id,
                    goal=str(payload.get("goal") or ""),
                    status="running",
                    device_id=str(payload.get("device_id") or "") or None,
                    context={"device_id": payload.get("device_id")},
                )
            elif event_type in {"TASK_COMPLETED", "TASK_FAILED", "task.aborted"}:
                status = "completed" if event_type == "TASK_COMPLETED" else "failed"
                await self.persistence.task_state(task_id, status=status, terminal_event=event_type)
            elif event_type == "task.waiting_approval":
                await self.persistence.task_state(task_id, status="waiting_approval")
            elif event_type in {"action.started", "ACTION"}:
                await self.persistence.task_state(task_id, status="running", current_action_id=action_id)
            elif event_type == "VERIFICATION":
                await self.persistence.task_state(task_id, status="verifying", last_verification=payload)
            elif event_type in {"recovery.decision", "plan.replanned"}:
                await self.persistence.task_state(task_id, status="recovering", recovery=payload)

        # The FastAPI application installs its LiveEventStream as the default
        # sink before accepting requests. Keeping this forwarding here means
        # planner/device/voice events cannot silently bypass the live UI.
        from .live_events import LiveEventStream

        stream = LiveEventStream.default()
        if stream is not None:
            live_payload = {key: value for key, value in payload.items() if key != "task_id"}
            await stream.publish(event_type, live_payload, task_id=task_id or None)


@dataclass(frozen=True)
class ActionLifecycle:
    task_id: str
    action_id: str
    tool: str
    status: str
    attempt: int = 0
    output: Any = None
    error: str | None = None
