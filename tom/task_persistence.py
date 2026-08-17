from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any

from .persistence import SupabaseTaskStore

_TERMINAL = {"TASK_COMPLETED", "TASK_FAILED", "task.aborted"}
_SECRET_KEYS = {"access_token", "refresh_token", "client_secret", "api_key", "auth_token", "password", "authorization"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if str(k).lower() in _SECRET_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class DurableTaskPersistence:
    """Durable task ledger with optional Supabase mirroring.

    Every runtime transition is append-only on local disk first, so a process
    crash cannot erase the execution history. Supabase is an optional durable
    remote mirror when configured. Recovery never replays an action merely
    because it was persisted as running: it restores the task as
    ``recovery_pending`` and requires a fresh observation/re-verification path.
    """

    def __init__(self, store: SupabaseTaskStore | None = None, path: str | Path | None = None) -> None:
        self.store = store
        self.path = Path(path or os.getenv("TOM_TASK_PERSISTENCE_PATH", "data/tasks.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @classmethod
    def from_environment(cls) -> "DurableTaskPersistence":
        store = None
        if os.getenv("TOM_SUPABASE_URL", "").strip() and os.getenv("TOM_SUPABASE_SERVICE_ROLE_KEY", "").strip():
            store = SupabaseTaskStore()
        return cls(store=store)

    def _append(self, record: dict[str, Any]) -> None:
        record = {"ts": time.time(), **_redact(record)}
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    async def event(self, task_id: str, sequence: int, event_type: str, payload: dict[str, Any], action_id: str | None = None) -> None:
        record = {"kind": "event", "task_id": task_id, "sequence": sequence, "event_type": event_type, "payload": payload}
        if action_id:
            record["action_id"] = action_id
        self._append(record)
        if self.store:
            await self.store.append_event(task_id=task_id, sequence=sequence, event_type=event_type, payload=_redact(payload), action_id=action_id)

    async def start_task(self, task_id: str, conversation_id: str, goal: str, status: str, device_id: str | None, context: dict[str, Any]) -> None:
        self._append({"kind": "task", "task_id": task_id, "status": status, "conversation_id": conversation_id, "goal": goal, "device_id": device_id, "context": context})
        if self.store:
            await self.store.create_task(task_id=task_id, conversation_id=conversation_id, goal=goal, status=status, device_id=device_id, context=_redact(context))

    async def task_state(self, task_id: str, **fields: Any) -> None:
        self._append({"kind": "task_state", "task_id": task_id, **fields})
        if self.store:
            await self.store.update_task(task_id, **fields)

    async def action_started(self, task_id: str, action_id: str, step: int, call: Any, attempt: int = 1, predicate: dict[str, Any] | None = None) -> None:
        payload = {"kind": "action", "task_id": task_id, "action_id": action_id, "step": step, "action_name": call.name, "arguments": dict(call.arguments), "risk": call.risk.value, "status": "running", "attempt": attempt, "predicate": predicate}
        self._append(payload)
        if self.store:
            await self.store.create_action(action_id=action_id, task_id=task_id, step=step, action_name=call.name, arguments=dict(call.arguments), risk=call.risk.value, status="running", attempt=attempt, predicate=predicate)

    async def action_finished(self, action_id: str, *, status: str, result: dict[str, Any] | None = None, predicate: dict[str, Any] | None = None, verification: dict[str, Any] | None = None, error: str | None = None) -> None:
        payload = {"kind": "action_state", "action_id": action_id, "status": status, "result": result, "predicate": predicate, "verification": verification, "error": error}
        self._append(payload)
        if self.store:
            await self.store.update_action(action_id, status=status, result=_redact(result), predicate=_redact(predicate), verification=_redact(verification), error=error, completed_at=None if status == "running" else "now()")

    def startup_recovery(self) -> dict[str, Any]:
        """Reconcile non-terminal persisted tasks without blindly re-executing them."""
        if not self.path.exists():
            return {"recovered": [], "count": 0}
        tasks: dict[str, dict[str, Any]] = {}
        actions: dict[str, dict[str, Any]] = {}
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            for line in lines[-10000:]:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                task_id = str(record.get("task_id") or "")
                if not task_id:
                    continue
                if record.get("kind") in {"task", "task_state"}:
                    tasks.setdefault(task_id, {}).update({k: v for k, v in record.items() if k not in {"kind", "ts"}})
                elif record.get("kind") == "event":
                    event_type = str(record.get("event_type") or "")
                    tasks.setdefault(task_id, {})["last_event"] = event_type
                    if event_type in _TERMINAL:
                        tasks[task_id]["status"] = "terminal"
                elif record.get("kind") in {"action", "action_state"}:
                    action_id = str(record.get("action_id") or "")
                    if action_id:
                        actions.setdefault(action_id, {}).update({k: v for k, v in record.items() if k not in {"kind", "ts"}})
        except OSError as exc:
            return {"recovered": [], "count": 0, "error": str(exc)}

        recovered: list[dict[str, Any]] = []
        for task_id, state in tasks.items():
            if state.get("status") in {"completed", "failed", "aborted", "terminal"}:
                continue
            item = {"task_id": task_id, "status": "recovery_pending", "last_event": state.get("last_event"), "goal": state.get("goal"), "device_id": state.get("device_id")}
            recovered.append(item)
        return {"recovered": recovered, "count": len(recovered), "policy": "observe_then_reverify; never replay a persisted action blindly"}

    async def recover(self, task_id: str) -> dict[str, Any] | None:
        if self.store:
            snapshot = await self.store.snapshot(task_id)
            if snapshot:
                return snapshot
        report = self.startup_recovery()
        for item in report["recovered"]:
            if item["task_id"] == task_id:
                return item
        return None
