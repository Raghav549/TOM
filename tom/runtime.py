from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .action_safety import ActionPreconditionChecker
from .agent_events import AgentEventBus
from .agent_state import StepState, TaskState
from .approval import ApprovalGate
from .execution_context import LiveExecutionContext
from .memory import MemoryStore
from .models import AgentRequest, AgentResponse, ToolCall, ToolResult
from .permissions import Decision, PermissionPolicy
from .planner import Planner
from .response import FriendlyFallback, Responder
from .tools import ToolRegistry
from .verifier import ExecutionVerifier


@dataclass
class AgentRuntime:
    planner: Planner
    tools: ToolRegistry
    memory: MemoryStore
    approvals: ApprovalGate
    policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    responder: Responder = field(default_factory=FriendlyFallback)
    verifier: ExecutionVerifier = field(default_factory=ExecutionVerifier)
    preconditions: ActionPreconditionChecker = field(default_factory=ActionPreconditionChecker)
    events_bus: AgentEventBus = field(default_factory=AgentEventBus)
    _pending: dict[str, list[ToolCall]] = field(default_factory=dict)
    _contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _tasks: dict[str, TaskState] = field(default_factory=dict)
    _live: dict[str, LiveExecutionContext] = field(default_factory=dict)

    async def handle(self, request: AgentRequest) -> AgentResponse:
        self.memory.add(request.conversation_id, "user", request.message, request.context)
        context = dict(request.context)
        context["memory"] = self.memory.recent(request.conversation_id)
        context["available_tools"] = self.tools.describe()
        plan = await self.planner.plan(request.message, context)
        task = TaskState(
            request.conversation_id,
            plan.goal,
            [StepState(i, c.name) for i, c in enumerate(plan.steps[:40])],
        )
        self._tasks[request.conversation_id] = task
        live = LiveExecutionContext(request.conversation_id, plan.goal)
        self._live[request.conversation_id] = live
        events: list[dict[str, Any]] = [{"type": "plan.created", "steps": len(task.steps), "progress": 0.0}]
        await self.events_bus.publish("plan.created", {"task_id": request.conversation_id, "goal": plan.goal})
        pending: list[ToolCall] = []
        results: list[ToolResult] = []

        for index, call in enumerate(plan.steps[: task.max_total_steps]):
            task.current_index = index
            decision = self.policy.decide(call, approved=False)
            if request.dry_run or decision is Decision.ASK:
                pending.append(call)
                task.steps[index].status = task.steps[index].status.BLOCKED
                events.append({"type": "approval.required", "tool": call.name, "risk": call.risk.value, "step": index})
                await self.events_bus.publish(
                    "approval.required",
                    {"task_id": request.conversation_id, "tool": call.name, "risk": call.risk.value},
                )
                continue
            if decision is Decision.DENY:
                task.steps[index].status = task.steps[index].status.ABORTED
                events.append({"type": "tool.denied", "tool": call.name, "risk": call.risk.value, "step": index})
                await self.events_bus.publish("tool.denied", {"task_id": request.conversation_id, "tool": call.name})
                continue

            task.start_current()
            result = await self._execute(
                call,
                events,
                context=context,
                conversation_id=request.conversation_id,
                step=index,
            )
            results.append(result)
            task.finish(result.success, error=result.error)
            if result.success:
                task.recover_or_advance()
            else:
                mode = task.recover_or_advance()
                events.append({"type": "recovery.decision", "step": index, "mode": mode, "attempts": task.steps[index].attempts})
                await self.events_bus.publish(
                    "recovery.decision",
                    {"task_id": request.conversation_id, "step": index, "mode": mode},
                )
                if mode == "abort":
                    break
            progress = task.progress()
            events.append({"type": "task.progress", "progress": progress, "step": index})
            await self.events_bus.publish("task.progress", {"task_id": request.conversation_id, "progress": progress})

        if pending:
            self._pending[request.conversation_id] = pending
            self._contexts[request.conversation_id] = context
        reply = await self.responder.respond(user_message=request.message, events=events, context=context)
        self.memory.add(request.conversation_id, "assistant", reply, {"events": events, "task": task.public_dict()})
        await self.events_bus.publish(
            "assistant.reply",
            {"task_id": request.conversation_id, "reply": reply, "pending": len(pending)},
        )
        return AgentResponse(
            conversation_id=request.conversation_id,
            reply=reply,
            plan=plan,
            pending_approval=pending,
            results=results,
            events=events,
        )

    def pending(self, conversation_id: str) -> list[ToolCall]:
        return list(self._pending.get(conversation_id, []))

    def task_state(self, conversation_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(conversation_id)
        if task is None:
            return None
        state = task.public_dict()
        live = self._live.get(conversation_id)
        if live:
            state["live"] = live.snapshot()
        return state

    def update_observation(
        self,
        conversation_id: str,
        *,
        package: str | None = None,
        url: str | None = None,
        fingerprint: str | None = None,
    ) -> dict[str, Any] | None:
        live = self._live.get(conversation_id)
        if live is None:
            return None
        live.observe(package=package, url=url, fingerprint=fingerprint)
        return live.snapshot()

    async def approve_and_execute(self, conversation_id: str, tool_index: int) -> dict[str, Any]:
        calls = self._pending.get(conversation_id, [])
        if tool_index < 0 or tool_index >= len(calls):
            raise IndexError("invalid pending tool index")
        call = calls[tool_index]
        self.approvals.approve(call)
        if not self.approvals.consume(call):
            raise RuntimeError("approval token could not be consumed")
        if self.policy.decide(call, approved=True) is not Decision.ALLOW:
            raise PermissionError("approved action was not allowed by policy")
        events: list[dict[str, Any]] = []
        context = dict(self._contexts.get(conversation_id, {}))
        context["approved"] = True
        result = await self._execute(call, events, context=context, conversation_id=conversation_id)
        del calls[tool_index]
        if not calls:
            self._pending.pop(conversation_id, None)
            self._contexts.pop(conversation_id, None)
        reply = await self.responder.respond(user_message="approved action", events=events, context=context)
        self.memory.add(conversation_id, "assistant", reply, {"events": events, "result": result.model_dump()})
        await self.events_bus.publish(
            "assistant.reply",
            {"task_id": conversation_id, "reply": reply, "pending": len(calls)},
        )
        return {"tool": call.name, "result": result.model_dump(), "reply": reply, "events": events}

    async def _execute(
        self,
        call: ToolCall,
        events: list[dict[str, Any]],
        *,
        context: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        approval_token: str | None = None,
        step: int = 0,
    ) -> ToolResult:
        action_id = str(uuid4())
        live = self._live.get(conversation_id or "")
        try:
            if live:
                live.action_started(action_id)
            await self.events_bus.publish(
                "action.started",
                {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "step": step},
            )
            tool = self.tools.get(call)
            arguments = dict(call.arguments)
            if call.name.startswith("device_"):
                device_id = str((context or {}).get("device_id", "")).strip()
                if device_id:
                    arguments.setdefault("device_id", device_id)
                if conversation_id:
                    arguments.setdefault("task_id", conversation_id)
                if approval_token:
                    arguments["approval_token"] = approval_token
            gated = call.model_copy(update={"arguments": arguments})
            pre = self.preconditions.check(gated, observed_state=(context or {}).get("screen_state"))
            if not pre.ok:
                if live:
                    live.action_finished(False, pre.reason)
                events.append({"type": "action.blocked", "tool": call.name, "reason": pre.reason})
                await self.events_bus.publish(
                    "action.finished",
                    {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "success": False, "error": pre.reason},
                )
                return ToolResult(tool=call.name, success=False, error=pre.reason)
            output = await tool.run(pre.normalized_arguments or arguments)
            result = ToolResult(tool=call.name, success=True, output=output)
            verification = self.verifier.verify(result)
            if not verification.ok:
                if live:
                    live.action_finished(False, verification.reason)
                events.append({"type": "tool.unverified", "tool": call.name, "reason": verification.reason})
                await self.events_bus.publish(
                    "action.finished",
                    {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "success": False, "error": verification.reason},
                )
                return ToolResult(tool=call.name, success=False, error=verification.reason)
            if live:
                live.action_finished(True)
            events.append({"type": "tool.completed", "tool": call.name, "verified": True})
            await self.events_bus.publish(
                "action.finished",
                {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "success": True, "output": output},
            )
            return result
        except Exception as exc:  # noqa: BLE001 - tool adapters are untrusted plugin boundaries
            if live:
                live.action_finished(False, str(exc))
            events.append({"type": "tool.failed", "tool": call.name, "error": str(exc)})
            await self.events_bus.publish(
                "action.finished",
                {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "success": False, "error": str(exc)},
            )
            return ToolResult(tool=call.name, success=False, error=str(exc))
