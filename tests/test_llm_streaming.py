from __future__ import annotations

import json

import httpx
import pytest

from tom.providers import OpenAICompatibleLLM
from tom.response import FriendlyFallback, ModelResponder


def _sse(*deltas: str, done: bool = True) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}\n\n" for d in deltas]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _llm(handler) -> OpenAICompatibleLLM:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    class PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = PatchedClient  # type: ignore[misc]
    llm = OpenAICompatibleLLM(base_url="http://llm.test/v1", api_key="k", model="qwen", backoff_seconds=0)
    return llm


@pytest.fixture(autouse=True)
def _restore_httpx_client():
    original = httpx.AsyncClient
    yield
    httpx.AsyncClient = original  # type: ignore[misc]


@pytest.mark.asyncio
async def test_stream_yields_deltas_incrementally_and_sets_headers() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_sse("Hel", "lo", " there"))

    llm = _llm(handler)
    deltas = [d async for d in llm.stream([{"role": "user", "content": "hi"}])]
    assert deltas == ["Hel", "lo", " there"]
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["stream"] is True
    assert seen["body"]["extra_body"] == {"enable_thinking": False}
    assert await llm.complete([{"role": "user", "content": "hi"}]) == "Hello there"


@pytest.mark.asyncio
async def test_retryable_status_is_retried_before_first_delta() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, content=b"busy", headers={"retry-after": "0"})
        return httpx.Response(200, content=_sse("ok"))

    llm = _llm(handler)
    assert await llm.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_non_retryable_error_is_surfaced() -> None:
    llm = _llm(lambda request: httpx.Response(401, content=b"nope"))
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await llm.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_empty_stream_is_an_error_not_silent_empty_reply() -> None:
    llm = _llm(lambda request: httpx.Response(200, content=_sse()))
    with pytest.raises(RuntimeError, match="no text content"):
        await llm.complete([{"role": "user", "content": "hi"}])


class _CompleteOnlyLLM:
    async def complete(self, messages, temperature=0.7):
        return "whole reply"


class _BrokenLLM:
    async def complete(self, messages, temperature=0.7):
        raise RuntimeError("provider down")

    async def stream(self, messages, temperature=0.7):
        raise RuntimeError("provider down")
        yield  # pragma: no cover


class _HalfwayLLM:
    async def stream(self, messages, temperature=0.7):
        yield "partial "
        raise RuntimeError("connection reset")


@pytest.mark.asyncio
async def test_model_responder_falls_back_to_complete_only_providers() -> None:
    responder = ModelResponder(_CompleteOnlyLLM(), FriendlyFallback())
    chunks = [c async for c in responder.stream(user_message="hi", events=[], context={})]
    assert chunks == ["whole reply"]


@pytest.mark.asyncio
async def test_model_responder_uses_fallback_when_provider_is_down() -> None:
    responder = ModelResponder(_BrokenLLM(), FriendlyFallback())
    chunks = [c async for c in responder.stream(user_message="kya haal", events=[], context={})]
    assert "".join(chunks) == "Haan bhai, maine suna: kya haal"
    assert await responder.respond(user_message="kya haal", events=[], context={}) == "Haan bhai, maine suna: kya haal"


@pytest.mark.asyncio
async def test_model_responder_does_not_append_fallback_after_partial_output() -> None:
    responder = ModelResponder(_HalfwayLLM(), FriendlyFallback())
    chunks = [c async for c in responder.stream(user_message="hi", events=[], context={})]
    assert chunks == ["partial "]
