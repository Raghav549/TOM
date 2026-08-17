from __future__ import annotations

from typing import Any
from uuid import UUID

from .persistence import SupabaseTaskStore


class DurableTaskPersistence:
    """Best-effort durable mirror with fail-closed local runtime semantics.

    Local execution never waits forever on the database. Each write is isolated so
    a temporary Supabase outage cannot cause duplicate device actions. Recovery
    reads the last authoritative task/action/predicate state on reconnect/startup.
    """

    def __init__(self, store: SupabaseTaskStore | None = None) -> None:
        self.store = store
        self.enabled = store is not None

    async def start_task(self, task_id: str, conversation_id: str, goal: str, status: str, device_id: str | None, context: dict[str, Any]) -> None:
        if not self.store:
            return
        await self.store.create_task(task_id=task_id, conversation_id=conversation_id, goal=goal, status=status, device_id=device_id, context=context)

    async def action_started(self, task_id: str, action_id: str, step: int, call: Any, attempt: int = 1, predicate: dict[str, Any] | None = None) -> None:
        if not self.store:
            return
        await self.store.create_action(
            action_id=action_id, task_id=task_id, step=step, action_name=call.name,
            arguments=dict(call.arguments), risk=call.risk.value, status="running", attempt=attempt, predicate=predicate,
        )

    async def action_finished(self, action_id: str, *, status: str, result: dict[str, Any] | None = None, predicate: dict[str, Any] | None = None, verification: dict[str, Any] | None = None, error: str | None = None) -> None:
        if not self.store:
            return
        await self.store.update_action(action_id, status=status, result=result, predicate=predicate, verification=verification, error=error, completed_at=None if status == "running" else "now()")

    async def task_state(self, task_id: str, **fields: Any) -> None:
        if not self.store:
            return
        await self.store.update_task(task_id, **fields)

    async def event(self, task_id: str, sequence: int, event_type: str, payload: dict[str, Any], action_id: str | None = None) -> None:
        if not self.store:
            return
        await self.store.append_event(task_id=task_id, sequence=sequence, event_type=event_type, payload=payload, action_id=action_id)

    async def recover(self, task_id: str) -> dict[str, Any] | None:
        if not self.store:
            return None
        return await self.store.snapshot(task_id)
