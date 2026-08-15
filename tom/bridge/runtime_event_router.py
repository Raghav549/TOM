from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from tom.execution.android_recovery_runtime import (
    AndroidActionRecoveryRuntime,
    AndroidExecutionResult,
)
from tom.perception.action_plan import GroundedActionPlan
from tom.perception.multimodal_observation import MultimodalObservation


@dataclass(frozen=True)
class BridgeEvent:
    type: str
    correlation_id: str
    payload: dict[str, Any]
    seq: int


class AndroidBridgeEventRouter:
    """Drives action recovery from authenticated bridge events.

    The router owns correlation IDs and converts transport events into the
    callbacks expected by the recovery state machine. Transport/authentication
    remains outside this class; only events accepted by that layer should enter.
    """

    def __init__(self, runtime: AndroidActionRecoveryRuntime) -> None:
        self.runtime = runtime
        self._pending: dict[str, asyncio.Future[BridgeEvent]] = {}
        self._seq = 0
        self._observations: dict[str, MultimodalObservation] = {}
        self._loop = asyncio.get_event_loop()

    async def on_event(self, event: BridgeEvent) -> None:
        if event.seq <= self._seq:
            return
        self._seq = event.seq
        waiter = self._pending.pop(event.correlation_id, None)
        if waiter and not waiter.done():
            waiter.set_result(event)
        if event.type == "observation":
            observation = event.payload.get("observation")
            if isinstance(observation, MultimodalObservation):
                self._observations[event.correlation_id] = observation

    async def _wait_for(self, correlation_id: str, send: Callable[[BridgeEvent], Awaitable[None]], request: BridgeEvent, timeout: float = 8.0) -> BridgeEvent | None:
        future: asyncio.Future[BridgeEvent] = self._loop.create_future()
        self._pending[correlation_id] = future
        await send(request)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending.pop(correlation_id, None)
            return None

    async def execute(
        self,
        plan: GroundedActionPlan,
        before: MultimodalObservation,
        send: Callable[[BridgeEvent], Awaitable[None]],
        verify_expected: Callable[[MultimodalObservation], bool],
        reground: Callable[[MultimodalObservation, GroundedActionPlan], Awaitable[GroundedActionPlan | None]],
        ask_user: Callable[[str], Awaitable[None]],
        task_id: str,
    ) -> AndroidExecutionResult:
        counter = 0

        async def dispatch(current: GroundedActionPlan, attempt: int) -> None:
            nonlocal counter
            counter += 1
            cid = f"{task_id}:action:{counter}"
            event = BridgeEvent(
                type="action_request",
                correlation_id=cid,
                seq=counter,
                payload={
                    "task_id": task_id,
                    "action_id": cid,
                    "action": current.action,
                    "node_id": current.node_id,
                    "bounds": list(current.bounds),
                    "attempt": attempt,
                    "confidence": current.confidence,
                },
            )
            response = await self._wait_for(cid, send, event)
            if response is None or response.type not in {"action_ack", "action_result"}:
                raise TimeoutError("Android action acknowledgement unavailable")

        async def observe(attempt: int) -> MultimodalObservation | None:
            nonlocal counter
            counter += 1
            cid = f"{task_id}:observation:{counter}"
            request = BridgeEvent(
                type="observation_request",
                correlation_id=cid,
                seq=counter,
                payload={"task_id": task_id, "reason": "post_action_verification", "attempt": attempt, "include_screenshot": True},
            )
            response = await self._wait_for(cid, send, request)
            if response is None or response.type != "observation":
                return None
            observation = response.payload.get("observation")
            return observation if isinstance(observation, MultimodalObservation) else None

        return await self.runtime.execute(plan, before, dispatch, observe, verify_expected, reground, ask_user)


# asyncio is imported after the public classes to keep the event model easy to read.
import asyncio
