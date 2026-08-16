from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol
import hashlib
import json

from .tool_registry import ToolRegistry
from .success_predicates import SuccessPredicateEngine, VerificationState
from .verification_policy import VerificationPolicy


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
    """Observe -> act -> action-specific verify -> recover/continue loop."""

    planner: Planner
    observer: Observer
    tools: ToolRegistry
    max_steps: int = 40
    max_same_action: int = 2
    max_verification_polls: int = 20
    on_event: Callable[[LoopEvent], Awaitable[None]] | None = None
    verifier: SuccessPredicateEngine = field(default_factory=SuccessPredicateEngine)
    verification_policy: VerificationPolicy = field(default_factory=VerificationPolicy)

    async def _emit(self, event: LoopEvent) -> None:
        if self.on_event:
            await self.on_event(event)

    @staticmethod
    def _fingerprint(state: Mapping[str, Any]) -> str:
        safe = json.dumps(state, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(safe.encode()).hexdigest()[:20]

    @staticmethod
    def _has_authoritative_evidence(observation: Mapping[str, Any]) -> bool:
        raw = observation.get("evidence")
        if not isinstance(raw, list):
            return False
        return any(bool(item.get("authoritative")) and float(item.get("confidence", 0)) >= 0.90 for item in raw if isinstance(item, Mapping))

    async def _verify_action(self, action: Mapping[str, Any], post_state: Mapping[str, Any]) -> Any:
        kind = str(action.get("kind", action.get("tool", "generic")))
        risk = str(action.get("risk", "reversible"))
        requirements = self.verification_policy.requirements(kind, risk)
        last_result = None
        for poll in range(self.max_verification_polls):
            last_result = self.verifier.verify(action, post_state)
            authoritative = self._has_authoritative_evidence(post_state)
            accepted = self.verification_policy.accept(
                last_result.state.value,
                last_result.confidence,
                requirements=requirements,
                authoritative=authoritative,
            )
            await self._emit(
                LoopEvent(
                    "verification_check",
                    "I am checking the action's expected postcondition.",
                    {
                        "tool": kind,
                        "poll": poll + 1,
                        "state": last_result.state.value,
                        "confidence": last_result.confidence,
                        "accepted": accepted,
                    },
                )
            )
            if accepted:
                return last_result
            if last_result.state is VerificationState.FAILED:
                return last_result
            post_state = await self.observer.observe()
        return last_result

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
                await self._emit(LoopEvent("stable_state", "The screen has not changed; I am checking for a grounded next step.", {"step": step}))
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
            verification = await self._verify_action(action, post_state)
            history[-1] = {
                **history[-1],
                "post_state": verification.observed if verification else post_state,
                "verification": {
                    "state": verification.state.value if verification else VerificationState.UNKNOWN.value,
                    "reason": verification.reason if verification else "verification unavailable",
                    "confidence": verification.confidence if verification else 0.0,
                },
            }

            if verification is None or verification.state is not VerificationState.VERIFIED:
                await self._emit(
                    LoopEvent(
                        "verification_failed",
                        "The action ran, but its expected outcome was not confirmed, so I will not assume success.",
                        {"tool": tool_name, "step": step, "state": verification.state.value if verification else "unknown"},
                    )
                )
                continue

            await self._emit(LoopEvent("verified", "The expected postcondition is confirmed.", {"tool": tool_name, "step": step}))

            if bool(action.get("done", False)):
                return {"status": "completed", "step": step, "history": history}

        return {"status": "max_steps", "history": history}
