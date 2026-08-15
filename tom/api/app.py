from __future__ import annotations

import asyncio
import html
import hmac
import os

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from tom.android_tools import register_android_tools
from tom.api.bridge_server import install_android_bridge
from tom.api.device_ws import build_device_websocket
from tom.api.voice_ws import build_live_voice_websocket
from tom.approval import ApprovalGate
from tom.companion import CompanionProfile
from tom.config import settings
from tom.credentials import CredentialManager
from tom.device.core_receiver import CoreBridgeReceiver
from tom.device_auth import DeviceAuthenticator
from tom.device_capabilities import DeviceCapabilityRegistry
from tom.google_oauth import GoogleOAuth
from tom.integration_registry import status as integration_status
from tom.live_events import LiveEventStream
from tom.live_task_bridge import LiveTaskBridge
from tom.memory import MemoryStore
from tom.models import AgentRequest
from tom.perception.pipeline import MultimodalRuntime
from tom.perception.vision_runtime import OpenAICompatibleVisionAdapter, VisionRuntimeConfig
from tom.permissions import Decision, PermissionPolicy
from tom.planner import ModelPlanner, RulePlanner
from tom.production import ProductionReadiness
from tom.providers import OpenAICompatibleLLM
from tom.public_api_catalog import catalog as public_api_catalog
from tom.public_api_catalog import executable_catalog
from tom.public_api_tools import register_public_api_tools
from tom.response import FriendlyFallback, ModelResponder
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry
from tom.voice.director import ConversationSignals
from tom.voice.engine import ExternalCommandSpeechEngine, SpeechEngineConfig
from tom.voice.models import VOICE_PROFILES
from tom.voice.session import VoiceSession

app = FastAPI(title="TOM Agent Runtime", version="1.0.0")
profile = CompanionProfile()
tools = ToolRegistry({})
credentials = CredentialManager(settings.data_dir)
device_capabilities = DeviceCapabilityRegistry.android_baseline()
fallback_planner = RulePlanner()
fallback_responder = FriendlyFallback()
readiness = ProductionReadiness()

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
live_events = LiveEventStream()
app.state.tom_live_events = live_events
live_tasks = LiveTaskBridge(planner, runtime.events_bus)

google_oauth = register_public_api_tools(tools, credentials)
app.state.tom_credentials = credentials
app.state.tom_google_oauth = google_oauth

vision_base_url = os.getenv("TOM_VISION_BASE_URL", "").strip()
vision_model = os.getenv("TOM_VISION_MODEL", "").strip()
vision_key = os.getenv("TOM_VISION_API_KEY", "")
vision_runtime = None
if vision_base_url and vision_model:
    vision_runtime = MultimodalRuntime(OpenAICompatibleVisionAdapter(VisionRuntimeConfig(vision_base_url, vision_key, vision_model)))


async def on_core_result(result: dict) -> None:
    task_id = str(result.get("task_id") or "")
    if task_id:
        await live_events.publish("verification.result", result, task_id=task_id)
        await android_bridge.resolve_verification(result)
        task_state = runtime.task_state(task_id) or {}
        goal = str(task_state.get("goal") or "")
        device_id = str(result.get("device_id") or task_state.get("device_id") or "")
        if goal and device_id:
            live_tasks.bind(task_id, goal, device_id)
        bound = live_tasks.tasks.get(task_id)
        if bound:
            replanned = await live_tasks.on_verification(result, tools.describe())
            if replanned is not None:
                await live_events.publish("plan.replanned", {"steps": len(replanned.steps), "goal": replanned.goal, "reason": "multimodal_verification_failed"}, task_id=task_id)
                for step in replanned.steps:
                    if not step.name.startswith("device_"):
                        continue
                    if runtime.policy.decide(step, approved=False) is not Decision.ALLOW:
                        await live_events.publish("replan.blocked", {"tool": step.name, "reason": "policy_or_approval_required"}, task_id=task_id)
                        break
                    context = {"device_id": bound.device_id, "available_tools": tools.describe()}
                    await runtime._execute(step, [], context=context, conversation_id=task_id)
                    break


core_receiver = CoreBridgeReceiver(vision_runtime, on_core_result) if vision_runtime is not None else None
android_bridge = install_android_bridge(app, event_stream=live_events, core_receiver=core_receiver)
register_android_tools(tools, android_bridge)

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


class CredentialProvisionRequest(BaseModel):
    provider: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    credentials: dict[str, str]


PROVISIONABLE_CREDENTIALS: dict[str, set[str]] = {
    "google_maps": {"api_key"},
    "aviationstack": {"api_key"},
    "marketstack": {"api_key"},
    "serpstack": {"api_key"},
    "mailboxlayer": {"api_key"},
    "twilio": {"account_sid", "auth_token", "from_number"},
}
credential_bearer = HTTPBearer(auto_error=False)


def require_credential_provisioner(auth: HTTPAuthorizationCredentials | None = Depends(credential_bearer)) -> None:  # noqa: B008
    expected = os.getenv("TOM_CREDENTIAL_PROVISION_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="credential provisioning is disabled; configure TOM_CREDENTIAL_PROVISION_TOKEN")
    if auth is None or auth.scheme.lower() != "bearer" or not auth.credentials or not hmac.compare_digest(auth.credentials, expected):
        raise HTTPException(status_code=401, detail="invalid credential provisioning token")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "tom", "version": "1.0.0"}


@app.get("/ready")
async def ready() -> dict[str, object]:
    return readiness.report()


@app.get("/v1/production/readiness")
async def production_readiness() -> dict[str, object]:
    return readiness.report()


@app.get("/v1/integrations")
async def integrations() -> dict[str, object]:
    return {"integrations": integration_status(), "note": "Unconfigured providers are never executed."}


@app.get("/v1/integrations/google/status")
async def google_integration_status() -> dict[str, object]:
    return google_oauth.status()


@app.get("/v1/integrations/google/connect")
async def google_connect() -> RedirectResponse:
    try:
        flow = google_oauth.begin()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(flow["authorization_url"], status_code=302)


@app.get("/v1/integrations/google/callback", response_class=HTMLResponse)
async def google_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> HTMLResponse:
    if error:
        message = html.escape(f"Google authorization was not completed: {error}")
        return HTMLResponse(f"<!doctype html><html><body><h2>TOM</h2><p>{message}</p><script>window.close()</script></body></html>", status_code=400)
    if not code or not state:
        return HTMLResponse("<!doctype html><html><body><h2>TOM</h2><p>Missing Google OAuth callback parameters.</p></body></html>", status_code=400)
    try:
        result = await google_oauth.exchange(code, state)
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        message = html.escape(str(exc))
        return HTMLResponse(f"<!doctype html><html><body><h2>TOM</h2><p>Google connection failed.</p><p>{message}</p></body></html>", status_code=400)
    web_origin = html.escape(os.getenv("TOM_WEB_ORIGIN", "http://localhost"), quote=True)
    payload = html.escape(str(result.get("scope", "")), quote=True)
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'><title>TOM Google Connected</title></head>"
        "<body><h2>Google connected</h2><p>TOM securely stored the OAuth credentials.</p>"
        f"<script>if(window.opener){{window.opener.postMessage({{type:'tom-google-connected',scopes:'{payload}'}},'{web_origin}');window.close();}}</script>"
        "</body></html>"
    )


@app.get("/v1/credentials/status")
async def credential_status() -> dict[str, object]:
    providers = sorted(PROVISIONABLE_CREDENTIALS)
    items = {}
    for provider in providers:
        value = credentials.get(provider) or {}
        items[provider] = {"configured": bool(value), "fields": sorted(value.keys())}
    return {"vault": {"configured": bool(os.getenv("TOM_CREDENTIAL_MASTER_KEY", "").strip()), "path": "credentials.enc"}, "providers": items, "google": google_oauth.status()}


@app.post("/v1/credentials", dependencies=[Depends(require_credential_provisioner)])
async def provision_credentials(request: CredentialProvisionRequest) -> dict[str, object]:
    allowed = PROVISIONABLE_CREDENTIALS.get(request.provider)
    if allowed is None:
        if request.provider == "google":
            raise HTTPException(status_code=409, detail="Google credentials are OAuth-managed; use /v1/integrations/google/connect")
        raise HTTPException(status_code=400, detail="provider is not provisionable")
    if not request.credentials or set(request.credentials) != allowed:
        raise HTTPException(status_code=400, detail=f"credential fields must exactly match: {sorted(allowed)}")
    if any(not str(value).strip() for value in request.credentials.values()):
        raise HTTPException(status_code=400, detail="credential values must not be empty")
    try:
        credentials.set(request.provider, {key: str(value).strip() for key, value in request.credentials.items()})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"provider": request.provider, "configured": True, "fields": sorted(request.credentials)}


@app.delete("/v1/credentials/{provider}", dependencies=[Depends(require_credential_provisioner)])
async def delete_credentials(provider: str) -> dict[str, object]:
    if provider not in PROVISIONABLE_CREDENTIALS:
        raise HTTPException(status_code=400, detail="provider is not provisionable")
    try:
        credentials.delete(provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"provider": provider, "configured": False}


@app.get("/v1/public-apis")
async def public_apis() -> dict[str, object]:
    return {"source": "public-apis/public-apis", "catalog": public_api_catalog(), "executable": executable_catalog(), "policy": "The upstream repository is discovery-only. Only typed, tested adapters are executable."}


@app.get("/v1/capabilities")
async def capabilities() -> dict:
    return {
        "core": [
            "planning", "structured_tool_calls", "tool_discovery", "execution_verification", "memory", "approval",
            "event_stream", "core_task_event_stream", "natural_response", "device_capability_discovery", "android_websocket_bridge",
            "real_android_action_tools", "correlated_post_action_verification", "real_public_api_tools", "public_api_catalog",
            "credential_vault", "credential_provisioning_api", "google_oauth_browser_flow",
            "multimodal_perception", "screenshot_chunk_reassembly", "semantic_visual_fusion",
            "screen_state_fingerprinting", "screen_change_detection", "multimodal_action_verification", "live_re_grounding", "live_replanning",
            "ocr_fallback_contract", "live_full_duplex_voice", "android_continuous_pcm_stream", "neural_vad", "streaming_asr",
            "partial_transcripts", "learned_turn_prediction", "continuous_prosody_state", "voice_barge_in", "partial_tts_cancellation", "streaming_tts",
            "production_readiness", "integration_registry", "correlated_verification_waiters",
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
        "communication_adapters": ["communication.sms_send"],
        "tools": tools.describe(),
        "note": "Only configured adapters are executable; TOM never simulates unavailable capabilities.",
    }


@app.websocket("/v1/events/ws")
async def live_events_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    task_id = websocket.query_params.get("task_id")
    try:
        after = int(websocket.query_params.get("after", "0"))
    except ValueError:
        after = 0
    queue, replay = await live_events.subscribe(task_id=task_id, after=after)
    try:
        for event in replay:
            await websocket.send_json(event.as_dict())
        while True:
            event = await queue.get()
            if task_id and event.task_id not in {None, task_id}:
                continue
            await websocket.send_json(event.as_dict())
    except WebSocketDisconnect:
        pass
    finally:
        await live_events.unsubscribe(queue)


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


@app.get("/v1/tasks/{task_id}")
async def task_state(task_id: str) -> dict:
    state = runtime.task_state(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    return state


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
    response = await runtime.handle(request)
    goal = str(request.message)
    device_id = str(request.context.get("device_id", "")).strip()
    if device_id:
        live_tasks.bind(request.conversation_id, goal, device_id)
        await live_events.publish("task.started", {"goal": goal, "device_id": device_id}, task_id=request.conversation_id)
    for event in response.events:
        await live_events.publish(event.get("type", "task.event"), event, task_id=request.conversation_id)
    return response


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
