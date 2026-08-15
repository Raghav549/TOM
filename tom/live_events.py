from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


TERMINAL_TYPES = {"task.completed", "task.failed", "TASK_COMPLETED", "TASK_FAILED"}


def _voice_text(event_type: str, payload: dict[str, Any]) -> str:
    message = str(payload.get("message") or payload.get("reply") or "")
    if event_type in {"task.started", "TASK_STARTED"}:
        return "Haan bhai, main kaam shuru kar raha hoon."
    if event_type in {"task.progress", "LIVE_PROGRESS"}:
        return str(payload.get("message") or "Kaam chal raha hai.")
    if event_type in {"action.started", "action.requested", "ACTION"}:
        return str(payload.get("commentary") or f"{payload.get('tool') or payload.get('action') or 'action'} kar raha hoon.")
    if event_type in {"verification.started", "OBSERVATION"}:
        return "Screen check kar raha hoon."
    if event_type in {"verification.verified", "verification.result", "VERIFICATION"}:
        return "Check kar raha hoon ki kaam sahi hua ya nahi."
    if event_type in TERMINAL_TYPES:
        return message or ("Ho gaya bhai, kaam complete ho gaya." if "completed" in event_type.lower() else "Bhai, kaam complete nahi ho paya.")
    if event_type == "assistant.reply":
        return message
    return str(payload.get("voice_text") or "")


@dataclass(frozen=True)
class LiveEvent:
    seq: int
    type: str
    task_id: str | None
    payload: dict[str, Any]
    ts: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "type": self.type,
            "task_id": self.task_id,
            "payload": self.payload,
            "ts": self.ts,
        }


class LiveEventStream:
    """Single ordered source shared by Core, Android bridge, UI and voice."""

    def __init__(self, history_size: int = 512) -> None:
        self.history_size = history_size
        self._seq = 0
        self._history: list[LiveEvent] = []
        self._subscribers: set[asyncio.Queue[LiveEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, payload: dict[str, Any] | None = None, *, task_id: str | None = None) -> LiveEvent:
        data = dict(payload or {})
        if "voice_text" not in data:
            voice = _voice_text(event_type, data)
            if voice:
                data["voice_text"] = voice
        data.setdefault("terminal", event_type in TERMINAL_TYPES)
        async with self._lock:
            self._seq += 1
            event = LiveEvent(self._seq, event_type, task_id, data, time.time())
            self._history.append(event)
            if len(self._history) > self.history_size:
                del self._history[:-self.history_size]
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
        return event

    async def subscribe(self, *, task_id: str | None = None, after: int = 0) -> tuple[asyncio.Queue[LiveEvent], list[LiveEvent]]:
        queue: asyncio.Queue[LiveEvent] = asyncio.Queue(maxsize=128)
        async with self._lock:
            self._subscribers.add(queue)
            replay = [event for event in self._history if event.seq > after and (task_id is None or event.task_id in {None, task_id})]
        return queue, replay

    async def unsubscribe(self, queue: asyncio.Queue[LiveEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)
