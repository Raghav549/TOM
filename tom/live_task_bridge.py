from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_events import AgentEventBus
from .execution_context import LiveExecutionContext
from .live_loop import LiveDeviceLoop


@dataclass
class BoundLiveTask:
    task_id: str
    goal: str
    device_id: str
    loop: LiveDeviceLoop
    memory: list[dict[str, Any]] | None = None


class LiveTaskBridge:
    """Keeps one LiveDeviceLoop bound to each Core/Android task correlation."""

    def __init__(self, planner: Any, event_bus: AgentEventBus) -> None:
        self.planner = planner
        self.event_bus = event_bus
        self.tasks: dict[str, BoundLiveTask] = {}

    def bind(
        self,
        task_id: str,
        goal: str,
        device_id: str,
        *,
        memory: list[dict[str, Any]] | None = None,
        plan: Any | None = None,
    ) -> BoundLiveTask:
        current = self.tasks.get(task_id)
        if current:
            if memory is not None:
                current.memory = list(memory)
            if plan is not None:
                current.loop.activate(plan)
            return current
        context = LiveExecutionContext(task_id, goal)
        loop = LiveDeviceLoop(self.planner, self.event_bus, context)
        loop.activate(plan)
        bound = BoundLiveTask(task_id, goal, device_id, loop, list(memory or []))
        self.tasks[task_id] = bound
        return bound

    async def on_verification(self, result: dict[str, Any], tools: list[dict[str, Any]]) -> Any:
        task_id = str(result.get("task_id") or "")
        if not task_id:
            return None
        verification = result.get("verification") or {}
        status = str(verification.get("status") or "unknown")
        task = self.tasks.get(task_id)
        if task is None:
            return None
        delta = result.get("delta") or {}
        await task.loop.observation(
            package=str((result.get("state") or {}).get("package_name") or "unknown"),
            url=None,
            fingerprint=str((result.get("state") or {}).get("fingerprint") or ""),
            source="android.multimodal",
            task_id=task_id,
            action_id=result.get("action_id"),
            summary={"verification": verification, "delta": delta},
        )
        if status != "failed":
            return None
        return await task.loop.replan(goal=task.goal, memory=list(task.memory or []), tools=tools)

    async def stop(self, task_id: str, reason: str = "completed") -> None:
        task = self.tasks.pop(task_id, None)
        if task:
            await task.loop.stop(reason)
