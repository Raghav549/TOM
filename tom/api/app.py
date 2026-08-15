from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from tom.android_tools import register_android_tools
from tom.api.bridge_server import install_android_bridge
from tom.api.device_ws import build_device_websocket
from tom.api.voice_ws import build_live_voice_websocket
from tom.approval import ApprovalGate
from tom.companion import CompanionProfile
from tom.config import settings
from tom.device_auth import DeviceAuthenticator
from tom.device_capabilities import DeviceCapabilityRegistry
from tom.memory import MemoryStore
from tom.models import AgentRequest
from tom.perception.pipeline import MultimodalRuntime
from tom.perception.vision_runtime import OpenAICompatibleVisionAdapter, VisionRuntimeConfig
from tom.permissions import PermissionPolicy
from tom.planner import ModelPlanner, RulePlanner
from tom.providers import OpenAICompatibleLLM
from tom.public_api_tools import register_public_api_tools
from tom.response import FriendlyFallback, ModelResponder
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry
from tom.voice.director import ConversationSignals
from tom.voice.engine import ExternalCommandSpeechEngine, SpeechEngineConfig
from tom.voice.models import VOICE_PROFILES
from tom.voice.session import VoiceSession

app = FastAPI(title="TOM Agent Runtime", version="0.9.0")
profile = CompanionProfile()
tools = ToolRegistry({})
device_capabilities = DeviceCapabilityRegistry.android_baseline()
fallback_planner = RulePlanner()
fallback_responder = FriendlyFallback()

if settings.llm_enabled:
    llm = OpenAICompatibleLLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    planner = ModelPlanner(llm, fallback_planner)
    responder = ModelResponder(llm, fallback_responder)
else:
    planner = fallback_planner
    responder = fallback_responder

runtime = AgentRuntime(planner, tools, MemoryStore(str(settings.data_dir)), ApprovalGate(settings.approval_required), PermissionPolicy(), responder)
device_auth = DeviceAuthenticator()
app.state.tom_device_auth = device_auth
app.state.tom_bridge_events = asyncio.Queue(maxsize=512)
android_bridge = install_android_bridge(app)
register_android_tools(tools, android_bridge)
register_public_api_tools(tools)

vision_base_url = os.getenv("TOM_VISION_BASE_URL", "").strip()
vision_model = os.getenv("TOM_VISION_MODEL", "").strip()
vision_key = os.getenv("TOM_VISION_API_KEY", "")
vision_runtime = None
if vision_base_url and vision_model:
    vision_runtime = MultimodalRuntime(OpenAICompatibleVisionAdapter(VisionRuntimeConfig(vision_base_url, vision_key, vision_model)))
if vision_runtime is not None:
    app.include_router(build_device_websocket(vision_runtime))

app.include_router(build_live_voice_websocket(runtime))
voice_session = VoiceSession(ExternalCommandSpeechEngine(SpeechEngineConfig()))


class ProfileUpdate(BaseModel):
    name: str | None = None
    interests: list[str] | None = None
    style: str | None = None
    language: str | None = None
    commentary_enabled: bool | None = None


class ApprovalRequest(BaseModel):
    conversation_id: str
    tool_index: int


class VoiceSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice_id: str = "tom_m1"
    situation: str = ""
    urgency: float = Field(default=0.0, ge=0.0, le=1.0)
    task_running: bool = False
    task_succeeded: bool = False
    task_failed: bool = False
    user_is_sad: bool = False
    user_is_excited: bool = False


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "tom", "version": "0.9.0"}


@app.get("/v1/capabilities")
async def capabilities() -> dict:
    return {
        "core": [
            "planning", "structured_tool_calls", "tool_discovery", "execution_verification", "memory", "approval",
            "event_stream", "natural_response", "device_capability_discovery", "android_websocket_bridge",
            "real_android_action_tools", "correlated_post_action_verification", "real_public_api_tools",
            "multimodal_perception", "screenshot_chunk_reassembly", "semantic_visual_fusion",
            "screen_state_fingerprinting", "screen_change_detection", "ocr_fallback_contract",
            "live_full_duplex_voice", "android_continuous_pcm_stream", "neural_vad", "streaming_asr",
            "partial_transcripts", "learned_turn_prediction", "continuous_prosody_state",
            "voice_barge_in", "partial_tts_cancellation", "streaming_tts",
        ],
        "model_runtime": settings.llm_enabled,
        "vision_runtime": vision_runtime is not None,
        "voice_profiles": list(VOICE_PROFILES),
        "voice_languages": ["hi", "en", "hinglish", "bn"],
        "voice_engine": bool(os.getenv("TOM_TTS_COMMAND", "").strip()),
        "streaming_voice_engine": bool(os.getenv("TOM_COSYVOICE_MODEL_DIR", "").strip()),
        "asr_engine": bool(os.getenv("TOM_ASR_MODEL", "").strip()),
        "neural_vad": os.getenv("TOM_NEURAL_VAD", "1").lower() not in {"0", "false", "no"},
        "learned_turn_prediction": bool(os.getenv("TOM_TURN_MODEL_PATH", "").strip()),
        "device_capabilities": device_capabilities.describe(),
        "communication_adapters": [],
        "tools": tools.describe(),
        "note": "Only configured adapters are executable; TOM never simulates unavailable capabilities.",
    }


@app.post("/v1/voice/synthesize")
async def synthesize_voice(request: VoiceSynthesisRequest) -> Response:
    try:
        turn = voice_session.prepare_turn(request.text, voice_id=request.voice_id, signals=ConversationSignals(
            user_text=request.text, situation=request.situation, urgency=request.urgency,
            task_running=request.task_running, task_succeeded=request.task_succeeded,
            task_failed=request.task_failed, user_is_sad=request.user_is_sad, user_is_excited=request.user_is_excited,
        ))
        audio = voice_session.synthesize(turn)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")


@app.get("/v1/device/capabilities")
async def device_capability_status() -> dict:
    return {"capabilities": device_capabilities.describe()}


@app.get("/v1/device/sessions")
async def device_sessions() -> dict:
    return {"connected_devices": sorted(android_bridge.sessions)}


@app.get("/v1/profile")
async def get_profile() -> dict:
    return {"name": profile.name, "interests": sorted(profile.interests), "style": profile.style, "language": profile.language, "commentary_enabled": profile.commentary_enabled}


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
