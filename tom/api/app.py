from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from tom.approval import ApprovalGate
from tom.memory import MemoryStore
from tom.models import AgentRequest
from tom.planner import RulePlanner
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry

app = FastAPI(title="TOM Agent Runtime", version="0.1.0")
runtime = AgentRuntime(RulePlanner(), ToolRegistry({}), MemoryStore(), ApprovalGate(required=True))


class ApprovalRequest(BaseModel):
    conversation_id: str
    tool_index: int


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "tom"}


@app.post("/v1/agent")
async def agent(request: AgentRequest):
    return await runtime.handle(request)


@app.get("/v1/memory/{conversation_id}")
async def memory(conversation_id: str):
    return {"conversation_id": conversation_id, "items": runtime.memory.recent(conversation_id)}


@app.post("/v1/approval")
async def approve(request: ApprovalRequest):
    items = runtime.memory.recent(request.conversation_id)
    # Approval execution is intentionally not implicit; this endpoint only exists as the next
    # contract boundary. Tool-specific adapters must implement idempotent approval handling.
    raise HTTPException(status_code=501, detail="Tool adapter approval execution is not configured yet")
