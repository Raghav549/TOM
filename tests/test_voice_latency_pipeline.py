import asyncio

from tom.api.voice_ws import LiveVoiceConnection
from tom.models import AgentRequest
from tom.response import ModelResponder
from tom.runtime import AgentRuntime


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages, temperature=0.7):
        self.calls += 1
        return "fallback"

    async def stream(self, messages, temperature=0.7):
        for token in ("Hello", " there", "!", " How", " are", " you", "?"):
            await asyncio.sleep(0)
            yield token


class FakeResponder:
    async def respond(self, **kwargs):
        return "fallback"

    async def stream(self, **kwargs):
        for token in ("Hi", " there", "!"):
            yield token


class FakePlanner:
    def __init__(self):
        self.calls = 0

    async def plan(self, goal, context):
        self.calls += 1
        raise AssertionError("pure voice conversation should use the fast path")


def test_model_responder_streams_llm_deltas():
    async def run():
        responder = ModelResponder(FakeLLM(), FakeResponder())
        chunks = [chunk async for chunk in responder.stream(user_message="hi", events=[], context={})]
        assert "".join(chunks) == "Hello there! How are you?"

    asyncio.run(run())


def test_voice_phrase_boundary_prefers_punctuation_and_never_cuts_words():
    phrase, rest = LiveVoiceConnection._phrase_boundary("This is a natural first sentence. And the next one")
    assert phrase == "This is a natural first sentence."
    assert rest == "And the next one"


def test_runtime_voice_fast_path_skips_planner_for_chat():
    async def run():
        runtime = AgentRuntime(
            planner=FakePlanner(),
            tools=type("Tools", (), {"describe": lambda self: []})(),
            memory=type("Memory", (), {
                "add": lambda self, *args, **kwargs: None,
                "recent": lambda self, conversation_id: [],
            })(),
            approvals=type("Approvals", (), {})(),
            responder=FakeResponder(),
        )
        request = AgentRequest(message="How are you today?", conversation_id="voice-test", context={"voice_turn": True})
        chunks = [chunk async for chunk in runtime.stream_conversational_response(request)]
        assert "".join(chunks) == "Hi there!"
        assert runtime.planner.calls == 0

    asyncio.run(run())
