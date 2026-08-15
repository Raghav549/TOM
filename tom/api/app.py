from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from tom.approval import ApprovalGate
from tom.companion import CompanionProfile
from tom.config import settings
from tom.memory import MemoryStore
from tom.models import AgentRequest
from tom.permissions import PermissionPolicy
from tom.planner import RulePlanner
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry
from tom.voice import VOICES

app = FastAPI(title="TOM Agent Runtime", version="0.3.0")
profile = CompanionProfile()
runtime = AgentRuntime(
    RulePlanner(),
    ToolRegistry({}),
    MemoryStore(str(settings.data_dir)),
    ApprovalGate(settings.approval_required),
    PermissionPolicy(),
)


class ProfileUpdate(BaseModel):
    name: str | None = None
    interests: list[str] | None = None
    style: str | None = None
    language: str | None = None
    commentary_enabled: bool | None = None


class ApprovalRequest(BaseModel):
    conversation_id: str
    tool_index: int


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "tom", "version": "0.3.0"}


@app.get("/v1/capabilities")
async def capabilities() -> dict:
    return {
        "core": ["planning", "memory", "approval", "event_stream"],
        "voice_profiles": [voice.id for voice in VOICES],
        "device_adapters": [],
        "communication_adapters": [],
        "note": "Adapters are intentionally empty until configured; TOM never simulates unavailable capabilities.",
    }


@app.get("/v1/profile")
async def get_profile() -> dict:
    return {
        "name": profile.name,
        "interests": sorted(profile.interests),
        "style": profile.style,
        "language": profile.language,
        "commentary_enabled": profile.commentary_enabled,
    }


@app.put("/v1/profile")
async def update_profile(update: ProfileUpdate) -> dict:
    if update.name is not None:
        profile.name = update.name.strip() or "Tom"
    if update.interests is not None:
        profile.set_interests(update.interests)
    if update.style is not None:
        profile.style = update.style
    if update.language is not None:
        profile.language = update.language
    if update.commentary_enabled is not None:
        profile.commentary_enabled = update.commentary_enabled
    return await get_profile()


@app.post("/v1/agent")
async def agent(request: AgentRequest):
    return await runtime.handle(request)


@app.get("/v1/approvals/{conversation_id}")
async def pending_approvals(conversation_id: str):
    return {"conversation_id": conversation_id, "items": runtime.pending(conversation_id)}


@app.post("/v1/approval")
async def approve(request: ApprovalRequest):
    try:
        return await runtime.approve_and_execute(request.conversation_id, request.tool_index)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/v1/memory/{conversation_id}")
async def memory(conversation_id: str):
    return {"conversation_id": conversation_id, "items": runtime.memory.recent(conversation_id)}
