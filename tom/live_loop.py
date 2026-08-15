from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .agent_events import AgentEventBus
from .execution_context import LiveExecutionContext
from .models import Plan


@dataclass
class LiveDeviceLoop:
    """Connect device observations to replanning and user-visible commentary.

    The loop is intentionally transport-agnostic: the Android WSS adapter feeds
    observations/action results into it, while the planner/tool registry remain
    the source of executable decisions. No action is inferred from stale state.
    """

    planner: Any
    event_bus: AgentEventBus
    context: LiveExecutionContext
    commentary: Callable[[str], Awaitable[None]] | None = None
    _last_plan: Plan | None = field(default=None, init=False)
    _running: bool = field(default=False, init=False)

    async def start(self, goal: str, *, memory: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Plan:
        self._running = True
        await self.event_bus.publish("task.started", {"task_id": self.context.task_id, "goal": goal})
        plan = await self.planner.plan(
            goal,
            {
                "memory": memory,
                "available_tools": tools,
                "live_state": self.context.snapshot(),
            },
        )
        self._last_plan = plan
        await self.event_bus.publish(
            "plan.created",
            {
                "task_id": self.context.task_id,
                "steps": len(plan.steps),
                "goal": plan.goal,
            },
        )
        return plan

    async def observation(
        self,
        *,
        package: str,
        url: str | None,
        fingerprint: str,
        source: str,
        task_id: str | None = None,
        action_id: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        if not self._running:
            return
        self.context.observe(package=package, url=url, fingerprint=fingerprint)
        payload = {
            "task_id": task_id or self.context.task_id,
            "action_id": action_id,
            "package": package,
            "url": url,
            "fingerprint": fingerprint,
            "source": source,
            "summary": summary or {},
        }
        await self.event_bus.publish("observation.received", payload)
        await self.event_bus.publish("screen.changed", payload)
        if self.commentary:
            await self.commentary("Ruk bhai, screen change hui hai—main fresh state dekh ke next step decide kar raha hoon.")

    async def action_result(self, *, action_id: str, success: bool, error: str | None = None) -> None:
        if not self._running:
            return
        self.context.action_finished(success, error)
        await self.event_bus.publish(
            "action.verified" if success else "action.failed",
            {
                "task_id": self.context.task_id,
                "action_id": action_id,
                "success": success,
                "error": error,
            },
        )
        if not success and self.commentary:
            await self.commentary("Ye step expected tarah nahi hua bhai; main dobara screen ground karke recover karta hoon.")

    async def replan(self, *, goal: str, memory: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Plan:
        if not self._running:
            raise RuntimeError("live loop is not running")
        plan = await self.planner.plan(
            goal,
            {
                "memory": memory,
                "available_tools": tools,
                "live_state": self.context.snapshot(),
                "previous_plan": self._last_plan.model_dump() if self._last_plan else None,
                "replan_reason": "fresh_observation",
            },
        )
        self._last_plan = plan
        await self.event_bus.publish(
            "plan.replanned",
            {
                "task_id": self.context.task_id,
                "steps": len(plan.steps),
                "reason": "fresh_observation",
            },
        )
        return plan

    async def stop(self, reason: str = "completed") -> None:
        self._running = False
        await self.event_bus.publish("task.stopped", {"task_id": self.context.task_id, "reason": reason})
