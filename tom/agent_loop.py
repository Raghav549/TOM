from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol
import hashlib
import json

from .tool_registry import ToolRegistry


class Planner(Protocol):
    async def next_action(self, goal: str, state: Mapping[str, Any], history: list[Mapping[str, Any]]) -> Mapping[str, Any] | None: ...


class Observer(Protocol):
    async def observe(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class LoopEvent:
    kind: str
    message: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class AgentLoop:
    """ReAct-style observe -> act -> verify loop without exposing private reasoning traces."""

    planner: Planner
    observer: Observer
    tools: ToolRegistry
    max_steps: int = 40
    max_same_action: int = 2
    on_event: Callable[[LoopEvent], Awaitable[None]] | None = None

    async def _emit(self, event: LoopEvent) -> None:
        if self.on_event:
            await self.on_event(event)

    @staticmethod
    def _fingerprint(state: Mapping[str, Any]) -> str:
        safe = json.dumps(state, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(safe.encode()).hexdigest()[:20]

    async def run(self, goal: str) -> Mapping[str, Any]:
        if not goal.strip():
            return {"status": "invalid", "reason": "empty goal"}

        history: list[Mapping[str, Any]] = []
        seen_actions: dict[str, int] = {}
        previous_state_fp: str | None = None

        for step in range(1, self.max_steps + 1):
            state = await self.observer.observe()
            state_fp = self._fingerprint(state)
            await self._emit(LoopEvent("observed", "I checked the current screen/device state.", {"step": step}))

            if state_fp == previous_state_fp and step > 1:
                # The planner can still act, but repeated no-change loops are bounded.
                await self._emit(LoopEvent("stable_state", "The screen has not changed; I am checking for a safer next step.", {"step": step}))
            previous_state_fp = state_fp

            action = await self.planner.next_action(goal, state, history)
            if not action:
                await self._emit(LoopEvent("blocked", "I cannot find a grounded next action yet."))
                return {"status": "blocked", "step": step, "history": history}

            tool_name = str(action.get("tool", ""))
            args = action.get("arguments", {})
            if not isinstance(args, Mapping):
                return {"status": "failed", "reason": "tool arguments must be an object", "history": history}

            action_key = json.dumps({"tool": tool_name, "arguments": dict(args)}, sort_keys=True, default=str)
            seen_actions[action_key] = seen_actions.get(action_key, 0) + 1
            if seen_actions[action_key] > self.max_same_action:
                await self._emit(LoopEvent("recovery", "That action is repeating without progress, so I am stopping instead of looping."))
                return {"status": "needs_recovery", "step": step, "history": history}

            confirmed = bool(action.get("confirmed", False))
            await self._emit(LoopEvent("acting", "I am doing the next step on the real device.", {"tool": tool_name, "step": step}))
            result = await self.tools.execute(tool_name, args, confirmed=confirmed)
            history.append({"step": step, "state": state, "action": dict(action), "result": dict(result)})

            if not result.get("ok"):
                await self._emit(LoopEvent("action_blocked", "That action needs permission or could not be executed.", {"tool": tool_name}))
                continue

            post_state = await self.observer.observe()
            history[-1] = {**history[-1], "post_state": post_state}
            await self._emit(LoopEvent("verified", "I checked what changed after the action.", {"tool": tool_name, "step": step}))

            if bool(action.get("done", False)):
                return {"status": "completed", "step": step, "history": history}

        return {"status": "max_steps", "history": history}
