"""Regression checks. Provider fixtures are protocol tests, not real inference."""
from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tom.approval import ApprovalGate
from tom.config import Settings
from tom.local_tools import WorkspaceTool
from tom.memory import MemoryStore
from tom.models import AgentRequest, Plan, Risk, ToolCall
from tom.planner import ModelPlanner, RulePlanner
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry
from tom.voice.qwen3_tts_stream import Qwen3TTSStreamingAdapter


def test_local_settings_do_not_require_key_and_refresh(monkeypatch):
    monkeypatch.setenv("TOM_LLM_ENABLED", "true")
    monkeypatch.delenv("TOM_LLM_API_KEY", raising=False)
    monkeypatch.delenv("TOM_LLM_MODEL", raising=False)
    monkeypatch.delenv("TOM_LLM_BASE_URL", raising=False)
    assert Settings().llm_enabled
    assert Settings().llm_model == "qwen3:4b"
    assert Settings().llm_base_url == "http://127.0.0.1:11434/v1"
    monkeypatch.setenv("TOM_LLM_MODEL", "my-installed-tag")
    assert Settings().llm_model == "my-installed-tag"


def test_model_risk_is_registry_authoritative():
    raw = json.dumps({"goal": "test", "steps": [{"name": "send", "risk": "read"}]})
    plan = ModelPlanner._parse(raw, "test", [{"name": "send", "risk": "high"}])
    assert plan.steps[0].risk is Risk.HIGH


def test_qwen_reasoning_is_not_confused_with_plan_json():
    plan = ModelPlanner._parse('<think>reason</think>\n{"goal":"chat","steps":[]}', "hello", [])
    assert plan.goal == "hello"


@pytest.mark.asyncio
async def test_fallback_is_explicit_and_cannot_invent_tools():
    class Broken:
        async def complete(self, *args, **kwargs):
            raise RuntimeError("offline")

    planner = ModelPlanner(Broken(), RulePlanner(), allow_fallback=False)
    with pytest.raises(RuntimeError, match="offline"):
        await planner.plan("search docs", {"available_tools": []})
    planner.allow_fallback = True
    with pytest.raises(RuntimeError, match="no supported recovery"):
        await planner.plan("search docs", {"available_tools": []})


class FixedPlan:
    def __init__(self, steps):
        self.steps = steps

    async def plan(self, goal, context):
        return Plan(goal=goal, steps=self.steps)


def runtime_for(tmp_path, steps, tool=None):
    return AgentRuntime(FixedPlan(steps), ToolRegistry({tool.name: tool} if tool else {}),
                        MemoryStore(str(tmp_path / "memory")), ApprovalGate())


@pytest.mark.asyncio
async def test_empty_plan_is_conversation_not_failed_task(tmp_path):
    runtime = runtime_for(tmp_path, [])
    result = await runtime.handle(AgentRequest(message="hello"))
    assert result.reply
    assert not any(event["type"].startswith("TASK_") for event in result.events)


@pytest.mark.asyncio
async def test_real_file_execution_and_approval_receipt(tmp_path):
    (tmp_path / "document.txt").write_text("real UTF-8 document: café", encoding="utf-8")
    tool = WorkspaceTool(tmp_path, "filesystem.read", "read text")
    call = ToolCall(name=tool.name, arguments={"path": "document.txt"})
    runtime = runtime_for(tmp_path, [call], tool)
    result = await runtime.handle(AgentRequest(message="read document", conversation_id="direct"))
    assert result.results[0].output["content"] == "real UTF-8 document: café"
    assert len(result.results[0].output["sha256"]) == 64
    assert result.events[-1]["type"] == "TASK_COMPLETED"
    queued = await runtime.handle(AgentRequest(message="read document", conversation_id="approved", dry_run=True))
    assert queued.pending_approval
    approved = await runtime.approve_and_execute("approved", 0)
    assert approved["result"]["success"]
    assert approved["events"][-1]["type"] == "TASK_COMPLETED"
    assert runtime.task_state("approved")["completed"]
    with pytest.raises(IndexError):
        await runtime.approve_and_execute("approved", 0)


@pytest.mark.asyncio
async def test_read_retry_and_no_dependent_execution_after_failure(tmp_path):
    class Intermittent:
        name, description, risk = "test.read", "test boundary", Risk.READ
        count = 0

        async def run(self, arguments):
            self.count += 1
            if self.count < 3:
                raise OSError("temporarily unavailable")
            return {"ok": True, "value": 42}

    tool = Intermittent()
    runtime = runtime_for(tmp_path, [ToolCall(name=tool.name)], tool)
    result = await runtime.handle(AgentRequest(message="read"))
    assert tool.count == 3
    assert result.events[-1]["type"] == "TASK_COMPLETED"
    missing = ToolCall(name="not.installed")
    runtime = runtime_for(tmp_path, [missing, ToolCall(name=tool.name)], tool)
    result = await runtime.handle(AgentRequest(message="read"))
    assert tool.count == 3
    assert result.events[-1]["type"] == "TASK_FAILED"
    assert "unknown tool" in result.events[-1]["errors"][0]


@pytest.mark.asyncio
async def test_cancellation_releases_conversation_slot(tmp_path):
    started = asyncio.Event()

    class Waiting:
        name, description, risk = "test.wait", "test boundary", Risk.READ

        async def run(self, arguments):
            started.set()
            await asyncio.Event().wait()

    tool = Waiting()
    runtime = runtime_for(tmp_path, [ToolCall(name=tool.name)], tool)
    request = AgentRequest(message="wait", conversation_id="same")
    running = asyncio.create_task(runtime.handle(request))
    await started.wait()
    with pytest.raises(RuntimeError, match="busy"):
        await runtime.handle(request)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert not runtime._active


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["../secret", ".env", "/etc/passwd"])
async def test_workspace_escape_rejected(tmp_path, path):
    tool = WorkspaceTool(tmp_path, "filesystem.read", "read text")
    with pytest.raises(PermissionError):
        await tool.run({"path": path})


@pytest.mark.asyncio
async def test_workspace_symlink_and_large_file_rejected(tmp_path):
    (tmp_path / "large").write_bytes(b"a" * 262145)
    (tmp_path / "link").symlink_to(tmp_path / "large")
    tool = WorkspaceTool(tmp_path, "filesystem.read", "read text")
    with pytest.raises(PermissionError):
        await tool.run({"path": "link"})
    with pytest.raises(ValueError, match="256 KiB"):
        await tool.run({"path": "large"})


def test_pcm16_is_little_endian_clipped_and_finite():
    convert = Qwen3TTSStreamingAdapter._to_pcm16_bytes
    assert convert(np.array([1, 32768, -32769])) == b"\x01\x00\xff\x7f\x00\x80"
    with pytest.raises(RuntimeError, match="non-finite"):
        convert(np.array([np.nan]))
    with pytest.raises(RuntimeError, match="even"):
        convert(b"x")


def test_corrupt_memory_does_not_destroy_valid_history(tmp_path, caplog):
    store = MemoryStore(str(tmp_path))
    store.add("c", "user", "valid")
    with store.path.open("a") as handle:
        handle.write("broken\n")
    assert store.recent("c")[0]["content"] == "valid"
    assert "corrupt memory" in caplog.text
    assert store.recent("c", 0) == []


def test_api_auth_and_private_context_rejection(monkeypatch):
    from tom.api.app import app

    monkeypatch.setenv("TOM_API_TOKEN", "test-only-token")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/v1/agent", json={"message": "hello"}).status_code == 401
        response = client.post("/v1/agent", headers={"Authorization": "Bearer test-only-token"},
                               json={"message": "hello", "context": {"_precomputed_plan": {}}})
        assert response.status_code == 422
        response = client.post("/v1/agent", headers={"Authorization": "Bearer test-only-token"}, json={"message": "hello"})
        assert response.status_code == 200
        assert not any(e["type"] == "TASK_FAILED" for e in response.json()["events"])


def test_tts_configured_token_enforced_in_development(monkeypatch):
    from fastapi import HTTPException

    from tom.voice.qwen3_tts_service import _authorize

    monkeypatch.setenv("TOM_ENV", "development")
    monkeypatch.setenv("TOM_QWEN3_TTS_AUTH_TOKEN", "local-token")
    with pytest.raises(HTTPException) as failure:
        _authorize(None)
    assert failure.value.status_code == 401
    _authorize("local-token")


@pytest.mark.asyncio
async def test_invalid_model_json_gets_one_repair_attempt():
    class Repairable:
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            return "invalid" if self.calls == 1 else '{"goal":"hello","steps":[]}'

    llm = Repairable()
    plan = await ModelPlanner(llm, RulePlanner(), allow_fallback=False).plan("hello", {})
    assert plan.goal == "hello"
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_failed_action_is_not_reported_successful_in_live_state(tmp_path):
    runtime = runtime_for(tmp_path, [ToolCall(name="unavailable")])
    await runtime.handle(AgentRequest(message="test", conversation_id="failed"))
    assert runtime.task_state("failed")["live"]["last_action_status"] == "failed"


def test_unknown_required_capability_fails_closed(monkeypatch):
    from tom.production import ProductionReadiness

    monkeypatch.setenv("TOM_REQUIRED_CAPABILITIES", "misspelled_model")
    report = ProductionReadiness().report()
    assert not report["ready"]
    assert report["failed_required_capabilities"] == ["misspelled_model"]


@pytest.mark.parametrize("path", ["/v1/events/ws", "/v1/voice/ws"])
def test_operator_websockets_require_configured_token(monkeypatch, path):
    from starlette.websockets import WebSocketDisconnect

    from tom.api.app import app

    monkeypatch.setenv("TOM_API_TOKEN", "test-socket-token")
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path):
            pass
