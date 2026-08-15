from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .approval import ApprovalGate
from .memory import MemoryStore
from .models import AgentRequest, AgentResponse, Risk
from .planner import RulePlanner
from .tools import ToolRegistry


@dataclass
class AgentRuntime:
    planner: RulePlanner
    tools: ToolRegistry
    memory: MemoryStore
    approvals: ApprovalGate

    async def handle(self, request: AgentRequest) -> AgentResponse:
        self.memory.add(request.conversation_id, "user", request.message, request.context)
        plan = await self.planner.plan(request.message, request.context)
        events: list[dict[str, Any]] = [{"type": "plan.created", "steps": len(plan.steps)}]
        pending = []
        results = []
        for call in plan.steps:
            if request.dry_run or self.approvals.needs_approval(call):
                pending.append(call)
                events.append({"type": "approval.required", "tool": call.name, "risk": call.risk.value})
                continue
            try:
                result = await self.tools.get(call).run(call.arguments)
                results.append({"tool": call.name, "result": result})
                events.append({"type": "tool.completed", "tool": call.name})
            except Exception as exc:
                events.append({"type": "tool.failed", "tool": call.name, "error": str(exc)})
        if pending:
            reply = "I have prepared the next steps. I need your approval before I perform the external action."
        elif results:
            reply = "I completed the available safe steps and recorded the results."
        else:
            reply = "I understood the request. No executable tool was required by the current runtime."
        self.memory.add(request.conversation_id, "assistant", reply, {"events": events})
        return AgentResponse(conversation_id=request.conversation_id, reply=reply, plan=plan, pending_approval=pending, events=events)
