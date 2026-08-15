from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .approval import ApprovalGate
from .memory import MemoryStore
from .models import AgentRequest, AgentResponse, ToolCall
from .permissions import Decision, PermissionPolicy
from .planner import Planner
from .tools import ToolRegistry


@dataclass
class AgentRuntime:
    planner: Planner
    tools: ToolRegistry
    memory: MemoryStore
    approvals: ApprovalGate
    policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    _pending: dict[str, list[ToolCall]] = field(default_factory=dict)

    async def handle(self, request: AgentRequest) -> AgentResponse:
        self.memory.add(request.conversation_id, "user", request.message, request.context)
        plan = await self.planner.plan(request.message, request.context)
        events: list[dict[str, Any]] = [{"type": "plan.created", "steps": len(plan.steps)}]
        pending: list[ToolCall] = []
        results: list[dict[str, Any]] = []

        for call in plan.steps:
            decision = self.policy.decide(call, approved=False)
            if request.dry_run or decision is Decision.ASK:
                pending.append(call)
                events.append({"type": "approval.required", "tool": call.name, "risk": call.risk.value})
                continue
            if decision is Decision.DENY:
                events.append({"type": "tool.denied", "tool": call.name, "risk": call.risk.value})
                continue
            result = await self._execute(call, events)
            if result is not None:
                results.append({"tool": call.name, "result": result})

        if pending:
            self._pending[request.conversation_id] = pending
            reply = "I’ve got the next step ready. Want me to go ahead?"
        elif results:
            reply = "Done bhai. I completed the available steps."
        else:
            reply = "I understood you, but there’s no configured tool for that yet."

        self.memory.add(request.conversation_id, "assistant", reply, {"events": events})
        return AgentResponse(
            conversation_id=request.conversation_id,
            reply=reply,
            plan=plan,
            pending_approval=pending,
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
        self.memory.add(conversation_id, "assistant", "Done bhai.", {"events": events})
        return {"tool": call.name, "result": result, "events": events}

    async def _execute(self, call: ToolCall, events: list[dict[str, Any]]) -> Any:
        try:
            result = await self.tools.get(call).run(call.arguments)
            events.append({"type": "tool.completed", "tool": call.name})
            return result
        except Exception as exc:
            events.append({"type": "tool.failed", "tool": call.name, "error": str(exc)})
            return None
