from __future__ import annotations

import os
from typing import Any, Mapping
from uuid import UUID

import httpx


class SupabaseTaskStore:
    """Durable task/action/event persistence for crash and reconnect recovery."""

    def __init__(self, url: str | None = None, service_key: str | None = None) -> None:
        self.url = (url or os.getenv("TOM_SUPABASE_URL", "")).rstrip("/")
        self.service_key = service_key or os.getenv("TOM_SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not self.service_key:
            raise RuntimeError("TOM_SUPABASE_URL and TOM_SUPABASE_SERVICE_ROLE_KEY are required")

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, table: str, *, params: Mapping[str, str] | None = None, json: Any = None) -> Any:
        async with httpx.AsyncClient(timeout=15.0, headers=self._headers()) as client:
            response = await client.request(method, f"{self.url}/rest/v1/{table}", params=params, json=json)
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()

    async def create_task(self, *, task_id: str, conversation_id: str, goal: str, status: str, device_id: str | None, context: dict[str, Any]) -> None:
        await self._request("POST", "tom_agent_tasks", params={"on_conflict": "id"}, json={"id": task_id, "conversation_id": conversation_id, "goal": goal, "status": status, "device_id": device_id, "context": context})

    async def update_task(self, task_id: str, **fields: Any) -> None:
        await self._request("PATCH", "tom_agent_tasks", params={"id": f"eq.{task_id}"}, json=fields)

    async def create_action(self, *, action_id: str, task_id: str, step: int, action_name: str, arguments: dict[str, Any], risk: str, status: str, attempt: int, grounded_target: dict[str, Any] | None = None, predicate: dict[str, Any] | None = None) -> None:
        await self._request("POST", "tom_agent_actions", json={"id": action_id, "task_id": task_id, "step": step, "action_name": action_name, "arguments": arguments, "risk": risk, "status": status, "attempt": attempt, "grounded_target": grounded_target, "predicate": predicate})

    async def update_action(self, action_id: str, **fields: Any) -> None:
        await self._request("PATCH", "tom_agent_actions", params={"id": f"eq.{action_id}"}, json=fields)

    async def append_event(self, *, task_id: str, sequence: int, event_type: str, payload: dict[str, Any], action_id: str | None = None) -> None:
        body = {"task_id": task_id, "sequence": sequence, "event_type": event_type, "payload": payload}
        if action_id:
            body["action_id"] = action_id
        await self._request("POST", "tom_agent_events", json=body)

    async def snapshot(self, task_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=15.0, headers=self._headers()) as client:
            response = await client.post(f"{self.url}/rest/v1/rpc/tom_task_snapshot", json={"p_task_id": task_id})
            response.raise_for_status()
            return response.json()

    async def active_tasks(self, conversation_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", "tom_agent_tasks", params={"conversation_id": f"eq.{conversation_id}", "status": "not.in.(completed,failed,aborted)", "order": "updated_at.desc"})
