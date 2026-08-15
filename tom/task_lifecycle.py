from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

TERMINAL = {"TASK_COMPLETED", "TASK_FAILED"}


@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    sequence: int
    type: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "sequence": self.sequence,
            "type": self.type,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass
class TaskLifecycle:
    """Authoritative task stream with replay-after-reconnect semantics.

    Events are retained in memory for the active task. The sequence number is
    monotonic and clients resume with last_seen_sequence. Consequential
    actions must publish ACTION_RESULT only after their executor/verification
    path reports the outcome.
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    max_events: int = 500
    _sequence: int = 0
    _events: list[TaskEvent] = field(default_factory=list)
    _subscribers: set[asyncio.Queue[TaskEvent]] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    terminal: str | None = None

    async def emit(self, event_type: str, **data: Any) -> TaskEvent:
        if self.terminal and event_type not in TERMINAL:
            raise RuntimeError(f"task {self.task_id} is already terminal")
        if event_type in TERMINAL and self.terminal and event_type != self.terminal:
            raise RuntimeError(f"task already terminated as {self.terminal}")
        async with self._lock:
            self._sequence += 1
            event = TaskEvent(self.task_id, self._sequence, event_type, time.time(), data)
            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]
            if event_type in TERMINAL:
                self.terminal = event_type
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            await queue.put(event)
        return event

    async def start(self, goal: str, **data: Any) -> TaskEvent:
        return await self.emit("TASK_STARTED", goal=goal, **data)

    async def progress(self, message: str, **data: Any) -> TaskEvent:
        return await self.emit("LIVE_PROGRESS", message=message, **data)

    async def action(self, action_id: str, action: str, **data: Any) -> TaskEvent:
        return await self.emit("ACTION", action_id=action_id, action=action, **data)

    async def observation(self, **data: Any) -> TaskEvent:
        return await self.emit("OBSERVATION", **data)

    async def verification(self, verified: bool, **data: Any) -> TaskEvent:
        return await self.emit("VERIFICATION", verified=verified, **data)

    async def complete(self, message: str, **data: Any) -> TaskEvent:
        return await self.emit("TASK_COMPLETED", message=message, **data)

    async def fail(self, message: str, **data: Any) -> TaskEvent:
        return await self.emit("TASK_FAILED", message=message, **data)

    async def replay(self, last_seen_sequence: int = 0) -> list[TaskEvent]:
        async with self._lock:
            return [event for event in self._events if event.sequence > last_seen_sequence]

    async def subscribe(self) -> asyncio.Queue[TaskEvent]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[TaskEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)


class TaskLifecycleRegistry:
    """Keeps active task streams addressable by task id for reconnecting clients."""

    def __init__(self, max_tasks: int = 256) -> None:
        self._tasks: dict[str, TaskLifecycle] = {}
        self._max_tasks = max_tasks
        self._lock = asyncio.Lock()

    async def create(self, goal: str, **data: Any) -> TaskLifecycle:
        task = TaskLifecycle()
        async with self._lock:
            if len(self._tasks) >= self._max_tasks:
                # Remove the oldest terminal task first; never evict an active task.
                terminal_ids = [task_id for task_id, item in self._tasks.items() if item.terminal]
                if terminal_ids:
                    del self._tasks[terminal_ids[0]]
                else:
                    raise RuntimeError("task registry capacity reached")
            self._tasks[task.task_id] = task
        await task.start(goal, **data)
        return task

    async def get(self, task_id: str) -> TaskLifecycle | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def remove(self, task_id: str) -> None:
        async with self._lock:
            self._tasks.pop(task_id, None)
