from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .task_lifecycle import TaskEvent, TaskLifecycle


@dataclass
class LiveResultBridge:
    """Fan out one authoritative task stream to UI and voice consumers.

    Both consumers receive the same ordered events. Reconnect clients should
    use TaskLifecycle.replay() before subscribing so a terminal result cannot
    disappear between disconnect and reconnect.
    """

    task: TaskLifecycle
    _ui: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    _voice: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    _forward_task: asyncio.Task[None] | None = None
    _source: asyncio.Queue[TaskEvent] | None = None

    async def start(self) -> None:
        if self._forward_task and not self._forward_task.done():
            return
        self._source = await self.task.subscribe()
        self._forward_task = asyncio.create_task(self._forward())

    async def stop(self) -> None:
        if self._source:
            await self.task.unsubscribe(self._source)
            self._source = None
        if self._forward_task:
            self._forward_task.cancel()
            await asyncio.gather(self._forward_task, return_exceptions=True)
            self._forward_task = None

    async def _forward(self) -> None:
        assert self._source is not None
        while True:
            event = await self._source.get()
            payload = self._render(event)
            for queue in tuple(self._ui):
                await queue.put(payload)
            if payload.get("voice_text"):
                for queue in tuple(self._voice):
                    await queue.put(payload)

    def _render(self, event: TaskEvent) -> dict[str, Any]:
        data = event.data
        message = str(data.get("message", ""))
        if event.type == "TASK_STARTED":
            voice = "Haan bhai, main kaam shuru kar raha hoon."
        elif event.type == "LIVE_PROGRESS":
            voice = message
        elif event.type == "ACTION":
            voice = f"{data.get('action', 'action')} kar raha hoon."
        elif event.type == "OBSERVATION":
            voice = "Screen check kar raha hoon."
        elif event.type == "VERIFICATION":
            voice = "Check kar raha hoon ki kaam sahi hua ya nahi."
        elif event.type == "TASK_COMPLETED":
            voice = message or "Ho gaya bhai, kaam complete ho gaya."
        elif event.type == "TASK_FAILED":
            voice = message or "Bhai, kaam complete nahi ho paya."
        else:
            voice = ""
        return {
            "type": "task_event",
            "task_id": event.task_id,
            "sequence": event.sequence,
            "event": event.type,
            "data": data,
            "voice_text": voice,
            "terminal": event.type in {"TASK_COMPLETED", "TASK_FAILED"},
        }

    async def subscribe_ui(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._ui.add(queue)
        return queue

    async def subscribe_voice(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._voice.add(queue)
        return queue

    def unsubscribe_ui(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._ui.discard(queue)

    def unsubscribe_voice(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._voice.discard(queue)


async def replay_for_ui_and_voice(task: TaskLifecycle, last_seen_sequence: int = 0) -> list[dict[str, Any]]:
    bridge = LiveResultBridge(task)
    return [bridge._render(event) for event in await task.replay(last_seen_sequence)]
