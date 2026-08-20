from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .action_safety import ActionPreconditionChecker
from .action_verification import ActionSpecificVerifier
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
    action_verifier: ActionSpecificVerifier = field(default_factory=ActionSpecificVerifier)
    preconditions: ActionPreconditionChecker = field(default_factory=ActionPreconditionChecker)
    events_bus: AgentEventBus = field(default_factory=AgentEventBus)
    _pending: dict[str, list[ToolCall]] = field(default_factory=dict)
    _contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _tasks: dict[str, TaskState] = field(default_factory=dict)
    _live: dict[str, LiveExecutionContext] = field(default_factory=dict)

    @staticmethod
    def _fresh_observation(result: ToolResult, context: dict[str, Any]) -> dict[str, Any]:
        """Prefer the executor's fresh observation over stale planner context.

        Device/browser executors may return ``observation``, ``post_observation``
        or ``screen_state_after`` alongside their ACK/result. Keeping this
        extraction in one place prevents a successful transport ACK from being
        mistaken for semantic success.
        """
        output = result.output if isinstance(result.output, dict) else {}
        for key in ("post_observation", "observation", "screen_state_after", "after"):
            value = output.get(key)
            if isinstance(value, dict):
                return dict(value)
        value = context.get("screen_state_after")
        return dict(value) if isinstance(value, dict) else {}

    async def handle(self, request: AgentRequest) -> AgentResponse:
        request_context = dict(request.context)
        skip_user_memory = bool(request_context.pop("_skip_user_memory", False))
        precomputed_plan = request_context.pop("_precomputed_plan", None)
        if not skip_user_memory:
            self.memory.add(request.conversation_id, "user", request.message, request_context)
        context = request_context
        context["memory"] = self.memory.recent(request.conversation_id)
        context["available_tools"] = self.tools.describe()
        plan = precomputed_plan if precomputed_plan is not None else await self.planner.plan(request.message, context)

        if plan.needs_clarification:
            question = plan.clarification_question.strip() or "Which option do you want me to use?"
            events = [{"type": "clarification.required", "question": question}]
            await self.events_bus.publish("clarification.required", {"task_id": request.conversation_id, "goal": request.message, "question": question})
            self.memory.add(request.conversation_id, "assistant", question, {"clarification": True})
            return AgentResponse(conversation_id=request.conversation_id, reply=question, plan=plan, events=events)

        task = TaskState(request.conversation_id, plan.goal, [StepState(i, c.name) for i, c in enumerate(plan.steps[:40])])
        self._tasks[request.conversation_id] = task
        live = LiveExecutionContext(request.conversation_id, plan.goal)
        self._live[request.conversation_id] = live
        device_id = str(request.context.get("device_id", "")).strip()
        events: list[dict[str, Any]] = [{"type": "TASK_STARTED", "goal": plan.goal, "device_id": device_id}]
        await self.events_bus.publish("TASK_STARTED", {"task_id": request.conversation_id, "goal": plan.goal, "device_id": device_id})
        pending: list[ToolCall] = []
        results: list[ToolResult] = []

        for index, call in enumerate(plan.steps[: task.max_total_steps]):
            task.current_index = index
            decision = self.policy.decide(call, approved=False)
            if request.dry_run or decision is Decision.ASK:
                pending.append(call)
                task.steps[index].status = task.steps[index].status.BLOCKED
                events.append({"type": "approval.required", "tool": call.name, "risk": call.risk.value, "step": index})
                await self.events_bus.publish("approval.required", {"task_id": request.conversation_id, "tool": call.name, "risk": call.risk.value})
                continue
            if decision is Decision.DENY:
                task.steps[index].status = task.steps[index].status.ABORTED
                events.append({"type": "tool.denied", "tool": call.name, "risk": call.risk.value, "step": index})
                await self.events_bus.publish("tool.denied", {"task_id": request.conversation_id, "tool": call.name})
                continue

            task.start_current()
            events.append({"type": "LIVE_PROGRESS", "message": f"{call.name} kar raha hoon.", "step": index})
            result = await self._execute(call, events, context=context, conversation_id=request.conversation_id, step=index)
            results.append(result)
            task.finish(result.success, error=result.error)
            if result.success:
                task.recover_or_advance()
            else:
                mode = task.recover_or_advance()
                events.append({"type": "recovery.decision", "step": index, "mode": mode, "attempts": task.steps[index].attempts})
                await self.events_bus.publish("recovery.decision", {"task_id": request.conversation_id, "step": index, "mode": mode, "attempts": task.steps[index].attempts})
                if mode == "abort":
                    break
            progress = task.progress()
            events.append({"type": "task.progress", "progress": progress, "step": index})
            await self.events_bus.publish("task.progress", {"task_id": request.conversation_id, "progress": progress, "step": index})

        if pending:
            self._pending[request.conversation_id] = pending
            self._contexts[request.conversation_id] = context
        reply = await self.responder.respond(user_message=request.message, events=events, context=context)
        self.memory.add(request.conversation_id, "assistant", reply, {"events": events, "task": task.public_dict()})

        if pending:
            await self.events_bus.publish("task.waiting_approval", {"task_id": request.conversation_id, "message": reply, "pending": len(pending), "terminal": False})
        else:
            completed = bool(results) and all(item.success for item in results) and task.completed
            terminal_type = "TASK_COMPLETED" if completed else "TASK_FAILED"
            events.append({"type": terminal_type, "message": reply, "goal": plan.goal})
            await self.events_bus.publish(terminal_type, {"task_id": request.conversation_id, "message": reply, "goal": plan.goal})
            await self.events_bus.publish("assistant.reply", {"task_id": request.conversation_id, "reply": reply, "pending": 0, "terminal": True})
        return AgentResponse(conversation_id=request.conversation_id, reply=reply, plan=plan, pending_approval=pending, results=results, events=events)

    async def stream_conversational_response(self, request: AgentRequest) -> AsyncIterator[str]:
        self.memory.add(request.conversation_id, "user", request.message, request.context)
        context = dict(request.context)
        context["memory"] = self.memory.recent(request.conversation_id)
        context["available_tools"] = self.tools.describe()
        voice_text = request.message.lower().strip()
        action_hints = (
            "open ", "launch ", "search ", "find ", "look up", "check ", "send ", "message ", "email ",
            "call ", "buy ", "purchase ", "order ", "pay ", "payment", "book ", "navigate ", "map ",
            "play ", "pause ", "download ", "install ", "delete ", "remove ", "set ", "turn on", "turn off",
            "remind me", "screenshot", "tap ", "click ", "scroll ", "go back", "website", "calendar",
            "schedule", "whatsapp", "instagram", "upi", "location", "weather", "price", "stock",
        )
        fast_chat = bool(request.context.get("voice_turn")) and not any(hint in voice_text for hint in action_hints)
        if fast_chat:
            chunks: list[str] = []
            async for token in self.responder.stream(user_message=request.message, events=[], context=context):
                if not token:
                    continue
                chunks.append(token)
                await self.events_bus.publish("assistant.partial", {"task_id": request.conversation_id, "text": token})
                yield token
            reply = "".join(chunks).strip()
            if reply:
                self.memory.add(request.conversation_id, "assistant", reply, {"streamed": True, "voice_fast_path": True})
                await self.events_bus.publish("assistant.reply", {"task_id": request.conversation_id, "reply": reply, "pending": 0, "terminal": True})
            return
        plan = await self.planner.plan(request.message, context)
        if plan.needs_clarification:
            question = plan.clarification_question.strip() or "Which option do you want me to use?"
            self.memory.add(request.conversation_id, "assistant", question, {"clarification": True})
            await self.events_bus.publish("clarification.required", {"task_id": request.conversation_id, "goal": request.message, "question": question})
            yield question
            return
        if plan.steps:
            response = await self.handle(AgentRequest(message=request.message, conversation_id=request.conversation_id, context={**request.context, "_skip_user_memory": True, "_precomputed_plan": plan}, dry_run=request.dry_run))
            yield response.reply
            return
        chunks: list[str] = []
        async for token in self.responder.stream(user_message=request.message, events=[], context=context):
            if not token:
                continue
            chunks.append(token)
            await self.events_bus.publish("assistant.partial", {"task_id": request.conversation_id, "text": token})
            yield token
        reply = "".join(chunks).strip()
        if reply:
            self.memory.add(request.conversation_id, "assistant", reply, {"streamed": True})
            await self.events_bus.publish("assistant.reply", {"task_id": request.conversation_id, "reply": reply, "pending": 0, "terminal": True})

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

    async def approve_and_execute(self, conversation_id: str, tool_index: int) -> dict[str, Any]:
        calls = self._pending.get(conversation_id, [])
        if tool_index < 0 or tool_index >= len(calls):
            raise IndexError("invalid pending tool index")
        call = calls[tool_index]
        token = self.approvals.approve(call)
        if not self.approvals.consume(call):
            raise RuntimeError("approval token could not be consumed")
        if self.policy.decide(call, approved=True) is not Decision.ALLOW:
            raise PermissionError("approved action was not allowed by policy")
        events: list[dict[str, Any]] = []
        context = dict(self._contexts.get(conversation_id, {}))
        context["approved"] = True
        result = await self._execute(call, events, context=context, conversation_id=conversation_id, approval_token=token.token)
        del calls[tool_index]
        if not calls:
            self._pending.pop(conversation_id, None)
            self._contexts.pop(conversation_id, None)
        reply = await self.responder.respond(user_message="approved action", events=events, context=context)
        self.memory.add(conversation_id, "assistant", reply, {"events": events, "result": result.model_dump()})
        terminal = not calls
        if terminal:
            verification_ok = result.success
            terminal_type = "TASK_COMPLETED" if verification_ok else "TASK_FAILED"
            events.append({"type": terminal_type, "message": reply, "verified": verification_ok})
            await self.events_bus.publish(terminal_type, {"task_id": conversation_id, "message": reply, "verified": verification_ok})
        await self.events_bus.publish("assistant.reply", {"task_id": conversation_id, "reply": reply, "pending": len(calls), "terminal": terminal})
        return {"tool": call.name, "result": result.model_dump(), "reply": reply, "events": events}

    async def _execute(self, call: ToolCall, events: list[dict[str, Any]], *, context: dict[str, Any] | None = None, conversation_id: str | None = None, approval_token: str | None = None, step: int = 0) -> ToolResult:
        action_id = str(uuid4())
        live = self._live.get(conversation_id or "")
        try:
            if live:
                live.action_started(action_id)
            events.append({"type": "ACTION", "action_id": action_id, "action": call.name, "step": step})
            await self.events_bus.publish("action.started", {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "step": step})
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
                    live.action_finished(action_id, False)
                error = pre.reason or "action precondition failed"
                events.append({"type": "action.failed", "action_id": action_id, "error": error, "step": step})
                await self.events_bus.publish("action.failed", {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "error": error, "step": step})
                return ToolResult(tool=call.name, success=False, output=None, error=error)
            before_state = dict((context or {}).get("screen_state") or {})
            result = await tool.run(gated.arguments)
            after_state = self._fresh_observation(result, {})
            predicate = self.action_verifier.verify(gated, result, before=before_state, after=after_state, provider=result.output if isinstance(result.output, dict) else {})
            events.append({"type": "VERIFICATION", "action_id": action_id, "tool": call.name, "verified": predicate.ok, "predicate": predicate.predicate, "confidence": predicate.confidence, "evidence": list(predicate.evidence), "reason": predicate.reason})
            await self.events_bus.publish("VERIFICATION", {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "verified": predicate.ok, "predicate": predicate.predicate, "confidence": predicate.confidence, "evidence": list(predicate.evidence), "reason": predicate.reason})
            if not predicate.ok:
                if live:
                    live.action_finished(action_id, False)
                error = f"verification failed: {predicate.reason}"
                events.append({"type": "action.failed", "action_id": action_id, "error": error, "step": step})
                await self.events_bus.publish("action.failed", {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "error": error, "step": step})
                return ToolResult(tool=call.name, success=False, output=result.output, error=error)
            if live:
                live.action_finished(action_id, True)
            events.append({"type": "action.finished", "action_id": action_id, "output": result.output, "verified": True, "step": step})
            await self.events_bus.publish("action.finished", {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "output": result.output, "verified": True, "step": step})
            return result
        except Exception as exc:  # noqa: BLE001 - tool adapters are an external failure boundary
            if live:
                live.action_finished(action_id, False)
            error = str(exc)
            events.append({"type": "action.failed", "action_id": action_id, "error": error, "step": step})
            await self.events_bus.publish("action.failed", {"task_id": conversation_id, "action_id": action_id, "tool": call.name, "error": error, "step": step})
            return ToolResult(tool=call.name, success=False, output=None, error=error)
