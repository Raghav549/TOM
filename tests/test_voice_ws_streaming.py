from __future__ import annotations

import asyncio
import json
import time

import pytest

from tom.api import voice_ws
from tom.api.voice_ws import LiveVoiceConnection, _rms_threshold, _simple_vad
from tom.voice.cosyvoice_stream import TTSChunk


class FakeWebSocket:
    def __init__(self) -> None:
        self.text: list[dict] = []
        self.audio: list[bytes] = []
        self.closed = False

    async def send_text(self, data: str) -> None:
        if self.closed:
            raise RuntimeError("closed")
        self.text.append(json.loads(data))

    async def send_bytes(self, data: bytes) -> None:
        if self.closed:
            raise RuntimeError("closed")
        self.audio.append(data)

    def events(self, kind: str) -> list[dict]:
        return [event for event in self.text if event["type"] == kind]


class FakeTTS:
    def __init__(self, *, fail_language: str | None = None) -> None:
        self.spoken: list[str] = []
        self.fail_language = fail_language

    def stream(self, text, *, language, voice, style):
        if self.fail_language and language.value == self.fail_language:
            raise RuntimeError("unsupported language")
        self.spoken.append(text)
        yield TTSChunk(pcm16=b"\x01\x00" * 480, sample_rate=24000)


class FakeASR:
    def __init__(self, text: str = "hello tom") -> None:
        self.text = text

    def reset(self) -> None:
        pass

    def load(self, pcm, sample_rate=16000) -> None:
        self.loaded = pcm

    def push(self, pcm, sample_rate=16000):
        return None

    def final(self, sample_rate=16000):
        return type("T", (), {"text": self.text, "confidence": 0.9, "language": "en"})()


class FakeRuntime:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.requests = []

    async def stream_conversational_response(self, request):
        self.requests.append(request)
        for token in self.tokens:
            await asyncio.sleep(0)
            yield token


@pytest.fixture
def connection(monkeypatch):
    def build(tokens: list[str], *, tts: FakeTTS | None = None) -> tuple[LiveVoiceConnection, FakeWebSocket]:
        fake_tts = tts or FakeTTS()
        monkeypatch.setattr(voice_ws, "build_streaming_tts", lambda: fake_tts)
        monkeypatch.setattr(voice_ws, "StreamingFasterWhisper", FakeASR)
        socket = FakeWebSocket()
        conn = LiveVoiceConnection(socket, FakeRuntime(tokens))
        conn.tts = fake_tts
        return conn, socket

    return build


def test_phrase_boundary_prefers_sentence_end_and_never_cuts_words() -> None:
    phrase, rest = LiveVoiceConnection._phrase_boundary("This is a natural first sentence. And the next one")
    assert phrase == "This is a natural first sentence."
    assert rest == "And the next one"

    phrase, rest = LiveVoiceConnection._phrase_boundary("too short")
    assert (phrase, rest) == ("", "too short")

    long_text = "word " * 60
    phrase, rest = LiveVoiceConnection._phrase_boundary(long_text.strip())
    assert phrase and not phrase.endswith("wor")
    assert (phrase + " " + rest).split() == long_text.split()

    phrase, rest = LiveVoiceConnection._phrase_boundary("ठीक है भाई, मैं देखता हूँ। अगला काम")
    assert phrase == "ठीक है भाई, मैं देखता हूँ।"
    assert rest == "अगला काम"


def test_simple_vad_and_threshold_mapping(monkeypatch) -> None:
    silence = b"\x00\x00" * 320
    loud = b"\x00\x10" * 320
    assert _simple_vad(silence, 180.0)[1] is False
    assert _simple_vad(loud, 180.0)[1] is True

    monkeypatch.delenv("TOM_VOICE_RMS_THRESHOLD", raising=False)
    monkeypatch.setenv("TOM_VAD_THRESHOLD", "0.55")
    assert _rms_threshold() == pytest.approx(1100.0)
    monkeypatch.setenv("TOM_VOICE_RMS_THRESHOLD", "300")
    assert _rms_threshold() == 300.0


@pytest.mark.asyncio
async def test_turn_streams_tts_per_phrase_while_llm_is_still_generating(connection) -> None:
    conn, socket = connection(["Hello there bhai, kaise ho aaj? ", "Main theek hoon.", " Bolo kya karna hai?"])
    await conn.process_turn(b"\x00\x01" * 8000)

    assert [e["text"] for e in socket.events("transcript")] == ["hello tom"]
    assert socket.events("response")[0]["text"] == "Hello there bhai, kaise ho aaj? Main theek hoon. Bolo kya karna hai?"
    assert conn.tts.spoken == ["Hello there bhai, kaise ho aaj?", "Main theek hoon. Bolo kya karna hai?"]
    assert len(socket.events("audio_start")) == 1
    assert len(socket.events("audio_end")) == 1
    assert len(socket.audio) == 2
    order = [e["type"] for e in socket.text]
    assert order.index("audio_start") < order.index("response"), "TTS must begin before the full LLM reply is complete"
    assert order[-1] == "state" and socket.text[-1]["value"] == "listening"


@pytest.mark.asyncio
async def test_tts_failure_reports_stage_and_keeps_session_alive(connection) -> None:
    conn, socket = connection(["नमस्ते भाई, आज क्या हाल है? "], tts=FakeTTS(fail_language="hi"))
    await conn.process_turn(b"\x00\x01" * 8000)

    errors = socket.events("error")
    assert errors and errors[0]["stage"] == "tts"
    assert socket.events("response"), "text reply must still reach the phone for its fallback TTS"
    assert not socket.audio
    assert socket.text[-1] == {"type": "state", "value": "listening"}


@pytest.mark.asyncio
async def test_short_turn_is_rejected_without_calling_asr(connection) -> None:
    conn, socket = connection(["unused"])
    await conn.process_turn(b"\x00" * 100)
    assert socket.events("error")[0]["detail"] == "audio_turn_too_short"
    assert not conn.runtime.requests


@pytest.mark.asyncio
async def test_hello_rejects_non_16k_input_without_closing(connection) -> None:
    conn, socket = connection([])
    await conn.handle_text(json.dumps({"type": "hello", "sample_rate": 44100}))
    assert socket.events("error")[0]["stage"] == "protocol"
    await conn.handle_text(json.dumps({"type": "hello", "sample_rate": 16000, "voice_id": "bogus"}))
    ready = socket.events("ready")[0]
    assert ready["voice_id"] == "tom_m1"
    assert ready["explicit_turn_control"] is True


@pytest.mark.asyncio
async def test_interrupt_cancels_speech_and_keeps_remainder_for_resume(connection) -> None:
    class SlowTTS(FakeTTS):
        def stream(self, text, *, language, voice, style):
            self.spoken.append(text)
            for _ in range(50):
                time.sleep(0.005)  # real synthesis is far slower than the event loop
                yield TTSChunk(pcm16=b"\x01\x00" * 480, sample_rate=24000)

    conn, socket = connection([], tts=SlowTTS())
    conn.tts_task = asyncio.create_task(conn._speak("First sentence is being spoken right now. Second sentence waits. Third one too."))
    await asyncio.sleep(0.02)
    await conn.handle_text(json.dumps({"type": "interrupt"}))

    stop = socket.events("audio_stop")[0]
    assert stop["cancelled"] is True
    assert conn.tom_speaking is False
    assert conn.pending_tts_text and "Second sentence waits." in conn.pending_tts_text

    await conn.handle_text(json.dumps({"type": "resume_audio"}))
    await conn.tts_task
    assert conn.tts.spoken[-1].endswith("Third one too.")


@pytest.mark.asyncio
async def test_unknown_message_type_is_reported(connection) -> None:
    conn, socket = connection([])
    await conn.handle_text("not json")
    await conn.handle_text(json.dumps({"type": "weird"}))
    details = [e["detail"] for e in socket.events("error")]
    assert details[0] == "invalid_json"
    assert "unknown message type" in details[1]
