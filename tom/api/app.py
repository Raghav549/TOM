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
from tom.browser_tools import register_browser_tools
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
            live_tasks.bind(
                task_id,
                goal,
                device_id,
                memory=runtime.memory.recent(task_id),
            )
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
browser_runtime = register_browser_tools(tools)
app.state.tom_browser_runtime = browser_runtime

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