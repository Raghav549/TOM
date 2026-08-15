from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .approval import ApprovalGate
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
    _pending: dict[str, list[ToolCall]] = field(default_factory=dict)

    async def handle(self, request: AgentRequest) -> AgentResponse:
        self.memory.add(request.conversation_id, "user", request.message, request.context)
        context = dict(request.context)
        context["memory"] = self.memory.recent(request.conversation_id)
        context["available_tools"] = self.tools.describe()
        plan = await self.planner.plan(request.message, context)
        events: list[dict[str, Any]] = [{"type": "plan.created", "steps": len(plan.steps)}]
        pending: list[ToolCall] = []
        results: list[ToolResult] = []

        for call in plan.steps:
            decision = self.policy.decide(call, approved=False)
            if request.dry_run or decision is Decision.ASK:
                pending.append(call)
                events.append({"type": "approval.required", "tool": call.name, "risk": call.risk.value})
                continue
            if decision is Decision.DENY:
                events.append({"type": "tool.denied", "tool": call.name, "risk": call.risk.value})
                continue
            results.append(await self._execute(call, events))

        if pending:
            self._pending[request.conversation_id] = pending
        reply = await self.responder.respond(user_message=request.message, events=events, context=context)
        self.memory.add(
            request.conversation_id,
            "assistant",
            reply,
            {"events": events, "results": [item.model_dump() for item in results]},
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
        result = await self._execute(call, events)
        del calls[tool_index]
        if not calls:
            self._pending.pop(conversation_id, None)
        reply = await self.responder.respond(user_message="approved action", events=events, context={})
        self.memory.add(conversation_id, "assistant", reply, {"events": events, "result": result.model_dump()})
        return {"tool": call.name, "result": result.model_dump(), "reply": reply, "events": events}

    async def _execute(self, call: ToolCall, events: list[dict[str, Any]]) -> ToolResult:
        try:
            tool = self.tools.get(call)
            output = await tool.run(call.arguments)
            result = ToolResult(tool=call.name, success=True, output=output)
            verification = self.verifier.verify(result)
            if not verification.ok:
                events.append({"type": "tool.unverified", "tool": call.name, "reason": verification.reason})
                return ToolResult(tool=call.name, success=False, error=verification.reason)
            events.append({"type": "tool.completed", "tool": call.name, "verified": True})
            return result
        except Exception as exc:  # noqa: BLE001 - tool adapters are untrusted plugin boundaries
            events.append({"type": "tool.failed", "tool": call.name, "error": str(exc)})
            return ToolResult(tool=call.name, success=False, error=str(exc))
