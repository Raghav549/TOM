"""Real, opt-in local-model certification probe; never substitutes fixture output.

Start TOM separately, set TOM_API_TOKEN, and run:
    python scripts/smoke_local_models.py
A nonzero exit means certification failed or a dependency is unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx

from tom.approval import ApprovalGate
from tom.config import Settings
from tom.local_tools import WorkspaceTool
from tom.memory import MemoryStore
from tom.models import AgentRequest
from tom.planner import ModelPlanner, RulePlanner
from tom.providers import OpenAICompatibleLLM
from tom.runtime import AgentRuntime
from tom.tools import ToolRegistry
from tom.voice.models import VOICE_PROFILES, Language, VoiceStyle
from tom.voice.qwen3_tts_stream import Qwen3TTSStreamingAdapter


async def main() -> int:
    checks: list[dict] = []

    async def check(name, operation):
        try:
            detail = await operation()
            checks.append({"name": name, "ok": True, "detail": detail})
        except Exception as exc:
            checks.append({"name": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

    settings = Settings()
    llm = OpenAICompatibleLLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model,
                              timeout_seconds=120, max_retries=0)

    async def inference():
        response = await llm.complete([{"role": "user", "content": "Reply with the word TOM_READY only. /no_think"}])
        if "TOM_READY" not in response:
            raise RuntimeError(f"Unexpected inference output: {response[:200]}")
        return {"model": llm.model, "response": response}

    async def agent_execution():
        with tempfile.TemporaryDirectory(prefix="tom-real-smoke-") as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("TOM_REAL_FILE_RECEIPT", encoding="utf-8")
            tool = WorkspaceTool(root, "filesystem.read", "Read UTF-8 text. arguments: {path: relative filename}")
            runtime = AgentRuntime(ModelPlanner(llm, RulePlanner(), allow_fallback=False),
                                   ToolRegistry({tool.name: tool}), MemoryStore(str(root / "memory")), ApprovalGate())
            result = await runtime.handle(AgentRequest(message="Use filesystem.read to read evidence.txt."))
            if not result.results or not all(item.success for item in result.results):
                raise RuntimeError(f"Agent did not complete: {result.model_dump_json()}")
            if result.results[0].output.get("content") != "TOM_REAL_FILE_RECEIPT":
                raise RuntimeError("File content receipt mismatch")
            return {"planner": "ModelPlanner", "events": result.events, "results": [r.model_dump() for r in result.results]}

    async def api():
        token = os.getenv("TOM_API_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(base_url=os.getenv("TOM_API_BASE_URL", "http://127.0.0.1:8787"), timeout=180, headers=headers) as client:
            health = await client.get("/health")
            health.raise_for_status()
            response = await client.post("/v1/agent", json={"message": "Say hello in one sentence. /no_think"})
            response.raise_for_status()
            if not response.json().get("reply"):
                raise RuntimeError("Agent API returned no reply")
            return {"health": health.json(), "agent": response.json()}

    def speech_sync():
        adapter = Qwen3TTSStreamingAdapter()
        size = 0
        for chunk in adapter.stream("This is a real local speech test.", language=Language.EN,
                                    voice=VOICE_PROFILES["tom_m1"], style=VoiceStyle()):
            if len(chunk.pcm16) % 2 or chunk.sample_rate != 24000:
                raise RuntimeError("Invalid PCM16 contract")
            size += len(chunk.pcm16)
        if not size:
            raise RuntimeError("No speech generated")
        return {"pcm16_bytes": size, "sample_rate": 24000, "note": "Contract check, not perceptual audio quality certification"}

    async def speech():
        return await asyncio.to_thread(speech_sync)

    await check("real_inference", inference)
    await check("real_model_planned_file_execution", agent_execution)
    await check("http_agent", api)
    await check("real_tts", speech)
    print(json.dumps(checks, indent=2))
    return 0 if all(item["ok"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
