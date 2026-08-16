from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from tom.agent_events import AgentEventBus


SpeakCallback = Callable[[str], Awaitable[None]]
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class LiveVoiceCommentary:
    """Turns verified runtime lifecycle events into short spoken progress updates."""

    def __init__(self, bus: AgentEventBus, task_id: str, speak: SpeakCallback, emit: EventCallback) -> None:
        self.bus = bus
        self.task_id = task_id
        self.speak = speak
        self.emit = emit
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self._handler = self._on_event

    async def _on_event(self, event: dict[str, Any]) -> None:
        if str(event.get("task_id") or "") == self.task_id:
            await self.queue.put(event)

    def start(self) -> None:
        self.bus.subscribe("*", self._handler)
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        spoken_action_ids: set[str] = set()
        while True:
            event = await self.queue.get()
            event_type = str(event.get("type", ""))
            action_id = str(event.get("action_id") or "")
            line = ""
            if event_type == "TASK_STARTED":
                line = "Theek hai, main kaam shuru kar raha hoon."
            elif event_type == "action.started" and action_id and action_id not in spoken_action_ids:
                spoken_action_ids.add(action_id)
                tool = str(event.get("tool") or "action")
                line = f"Ab {tool.replace('_', ' ')} kar raha hoon."
            elif event_type == "verification.started":
                line = "Abhi result verify kar raha hoon."
            elif event_type == "recovery.decision" and event.get("mode") not in {"abort", "none"}:
                line = "Ek recovery step le raha hoon, phir dobara check karta hoon."
            elif event_type == "action.finished" and event.get("success"):
                line = "Ho gaya, result mil gaya."
            elif event_type == "TASK_FAILED":
                line = "Is step mein problem aayi hai; main result ko guess nahi karunga."
            elif event_type == "verification.verified":
                line = "Result verify ho gaya."
            if line:
                await self.emit("voice_commentary", {"text": line, "event": event_type})
                await self.speak(line)

    async def stop(self) -> None:
        self.bus.unsubscribe("*", self._handler)
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
