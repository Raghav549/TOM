from __future__ import annotations

import asyncio
import json
import os
import re
import time
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tom.models import AgentRequest
from tom.runtime import AgentRuntime
from tom.voice.cosyvoice_stream import TTSChunk
from tom.voice.director import ConversationSignals
from tom.voice.models import VOICE_PROFILES
from tom.voice.session import VoiceSession
from tom.voice.streaming_asr import StreamingFasterWhisper
from tom.voice.tts_factory import build_streaming_tts
from tom.voice.prosody_state import ContinuousProsodyTracker

router = APIRouter(prefix="/v1/voice", tags=["voice"])


def _next_or_none(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return None


def _simple_vad(pcm: bytes, threshold: float = 650.0) -> tuple[float, bool]:
    if not pcm:
        return 0.0, False
    try:
        import numpy as np
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        energy = float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.0
        probability = min(1.0, energy / 4000.0)
        return probability, energy >= threshold
    except Exception:
        return 0.0, False


class LiveVoiceConnection:
    """Lightweight production voice transport.

    The Android client sends 16 kHz PCM16 frames. This server performs CPU-safe
    endpoint detection, ASR, LLM response generation and remote/local Qwen TTS.
    No Silero/ONNX dependency is required for the basic conversational path.
    """

    def __init__(self, websocket: WebSocket, runtime: AgentRuntime) -> None:
        self.websocket = websocket
        self.runtime = runtime
        self.asr = StreamingFasterWhisper()
        self.tts = build_streaming_tts()
        self.prosody = ContinuousProsodyTracker()
        self.conversation_id = str(uuid4())
        self.voice_id = "tom_m1"
        self.character_name = "TOM"
        self.character_style = "friendly+sigma"
        self.character_traits: tuple[str, ...] = ("helpful", "warm", "confident")
        self.audio_sample_rate = 16000
        self.pending_audio = bytearray()
        self.turn_audio = bytearray()
        self.pre_roll = bytearray()
        self.pre_roll_max = 5120
        self.in_speech = False
        self.silence_ms = 0
        self.speech_ms = 0
        self.last_partial_at_ms = 0
        self.tts_task: asyncio.Task | None = None
        self.turn_task: asyncio.Task | None = None
        self.pending_tts_text: str | None = None
        self.pending_tts_index = 0
        self.tom_speaking = False
        self._latency = {}

    async def send_event(self, event_type: str, **payload) -> None:
        await self.websocket.send_text(json.dumps({"type": event_type, **payload}, ensure_ascii=False))

    def _signals(self, *, user_text: str) -> ConversationSignals:
        state = self.prosody.state
        return ConversationSignals(
            user_text=user_text,
            user_is_excited=state.arousal >= 0.58,
            user_arousal=state.arousal,
            user_valence=state.valence_hint,
            character_name=self.character_name,
            character_style=self.character_style,
            character_traits=self.character_traits,
            character_pitch_shift=None,
            character_speaking_rate=None,
            character_warmth=None,
            character_breathiness=None,
            character_expressiveness=None,
        )

    async def _speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        segments = [x.strip() for x in re.split(r"(?<=[.!?।])\s+", text) if x.strip()]
        signals = self._signals(user_text="")
        selected = self.voice_id if self.voice_id in VOICE_PROFILES else "tom_m1"
        self.tom_speaking = True
        await self.send_event("audio_start", sample_rate=24000, channels=1, encoding="pcm_s16le", voice_id=selected, streaming=True)
        try:
            for segment in segments:
                turn = VoiceSession(self.tts).prepare_turn(segment, voice_id=selected, signals=signals)
                iterator = self.tts.stream(segment, language=turn.language, voice=VOICE_PROFILES[selected], style=turn.style)
                while True:
                    chunk: TTSChunk | None = await asyncio.to_thread(_next_or_none, iterator)
                    if chunk is None:
                        break
                    await self.websocket.send_bytes(chunk.pcm16)
                    await asyncio.sleep(0)
        finally:
            self.tom_speaking = False
            await self.send_event("audio_end")

    async def process_turn(self, pcm: bytes) -> None:
        if len(pcm) < 6400:
            return
        await self.send_event("state", value="transcribing")
        self.asr.reset()
        self.asr._buffer.extend(pcm)
        try:
            final = await asyncio.to_thread(self.asr.final, 16000)
        except Exception as exc:
            await self.send_event("error", stage="asr", detail=str(exc))
            await self.send_event("state", value="listening")
            return
        text = final.text.strip()
        if not text:
            await self.send_event("state", value="listening")
            return
        await self.send_event("transcript", text=text, confidence=final.confidence, language=final.language, final=True)
        await self.send_event("state", value="thinking")
        request = AgentRequest(
            message=text,
            conversation_id=self.conversation_id,
            context={
                "voice_turn": True,
                "asr_confidence": final.confidence,
                "user_language": final.language,
                "companion_name": self.character_name,
                "companion_style": self.character_style,
                "companion_traits": list(self.character_traits),
            },
        )
        try:
            response_parts: list[str] = []
            async for token in self.runtime.stream_conversational_response(request):
                if token:
                    response_parts.append(token)
                    await self.send_event("response_partial", text=token)
            response = "".join(response_parts).strip()
            if not response:
                raise RuntimeError("LLM returned an empty response")
            await self.send_event("response", text=response, conversation_id=self.conversation_id, streaming=True)
            self.tts_task = asyncio.create_task(self._speak(response))
            await self.tts_task
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.send_event("error", stage="voice_pipeline", detail=str(exc))
        finally:
            self.tts_task = None
            await self.send_event("state", value="listening")

    async def _process_frame(self, pcm: bytes) -> None:
        self.pre_roll.extend(pcm)
        if len(self.pre_roll) > self.pre_roll_max:
            del self.pre_roll[:-self.pre_roll_max]
        try:
            state = await asyncio.to_thread(self.prosody.update, pcm, 16000)
        except Exception:
            state = self.prosody.state
        probability, speech = _simple_vad(pcm)
        now_ms = int(time.time() * 1000)
        if speech:
            if not self.in_speech:
                self.in_speech = True
                self.silence_ms = 0
                self.speech_ms = 0
                self.turn_audio = bytearray(self.pre_roll)
                self.asr.reset()
                await self.send_event("state", value="listening")
            self.speech_ms += 20
            self.silence_ms = 0
            self.turn_audio.extend(pcm)
            if now_ms - self.last_partial_at_ms >= 800:
                self.last_partial_at_ms = now_ms
                try:
                    partial = await asyncio.to_thread(self.asr.push, pcm, 16000)
                    if partial and partial.text.strip():
                        await self.send_event("partial_transcript", text=partial.text, confidence=partial.confidence, language=partial.language)
                except Exception as exc:
                    await self.send_event("error", stage="partial_asr", detail=str(exc))
        elif self.in_speech:
            self.silence_ms += 20
            self.turn_audio.extend(pcm)
            if self.silence_ms >= 700 and self.speech_ms >= 200:
                self.in_speech = False
                turn = bytes(self.turn_audio)
                self.turn_audio.clear()
                self.silence_ms = 0
                self.speech_ms = 0
                if not self.turn_task or self.turn_task.done():
                    self.turn_task = asyncio.create_task(self.process_turn(turn))
        if now_ms % 1000 < 30:
            await self.send_event("prosody", continuous=True, energy=state.energy, arousal=state.arousal, valence_hint=state.valence_hint, vad_probability=probability)

    async def handle_text(self, message: str) -> None:
        payload = json.loads(message)
        event_type = payload.get("type", "")
        if event_type == "hello":
            self.voice_id = payload.get("voice_id", "tom_m1")
            self.audio_sample_rate = int(payload.get("sample_rate", 16000))
            if self.audio_sample_rate != 16000:
                raise ValueError("voice websocket input must be 16 kHz PCM16")
            character = payload.get("character") or {}
            if isinstance(character, dict):
                self.character_name = str(character.get("name") or "TOM").strip()[:64] or "TOM"
                self.character_style = str(character.get("style") or "friendly+sigma").strip()[:64] or "friendly+sigma"
                traits = character.get("traits") or ["helpful", "warm", "confident"]
                if isinstance(traits, str):
                    traits = [traits]
                self.character_traits = tuple(str(x).strip()[:48] for x in traits if str(x).strip())[:12]
            await self.send_event("ready", protocol=4, conversation_id=self.conversation_id, sample_rate=24000, continuous_audio=True, neural_vad=False, lightweight_vad=True, full_duplex=True, tts_engine=os.getenv("TOM_TTS_ENGINE", "qwen3"))
        elif event_type == "set_character":
            character = payload.get("character") or payload
            if isinstance(character, dict):
                self.character_name = str(character.get("name") or self.character_name).strip()[:64]
                self.character_style = str(character.get("style") or self.character_style).strip()[:64]
                traits = character.get("traits") or self.character_traits
                if isinstance(traits, str):
                    traits = [traits]
                self.character_traits = tuple(str(x).strip()[:48] for x in traits if str(x).strip())[:12]
            await self.send_event("character_updated", name=self.character_name, style=self.character_style, traits=list(self.character_traits))
        elif event_type == "audio_start":
            self.turn_audio.clear()
            self.in_speech = False
            self.silence_ms = 0
            self.speech_ms = 0
            self.asr.reset()
            await self.send_event("state", value="listening")
        elif event_type == "audio_end":
            if self.turn_audio and (not self.turn_task or self.turn_task.done()):
                turn = bytes(self.turn_audio)
                self.turn_audio.clear()
                self.in_speech = False
                self.turn_task = asyncio.create_task(self.process_turn(turn))
        elif event_type == "interrupt":
            if self.tts_task and not self.tts_task.done():
                self.tts_task.cancel()
                await asyncio.gather(self.tts_task, return_exceptions=True)
                self.tts_task = None
            self.tom_speaking = False
            await self.send_event("audio_stop", reason=payload.get("reason", "user_barge_in"), cancelled=True)
        elif event_type == "resume_audio":
            if self.pending_tts_text:
                self.tts_task = asyncio.create_task(self._speak(self.pending_tts_text))
            else:
                await self.send_event("resume", supported=False, reason="no resumable TTS")

    async def run(self) -> None:
        await self.send_event("connected", protocol=4)
        try:
            while True:
                message = await self.websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    await self.handle_text(message["text"])
                elif message.get("bytes") is not None:
                    self.pending_audio.extend(message["bytes"])
                    frame_bytes = 640
                    while len(self.pending_audio) >= frame_bytes:
                        frame = bytes(self.pending_audio[:frame_bytes])
                        del self.pending_audio[:frame_bytes]
                        await self._process_frame(frame)
        except WebSocketDisconnect:
            return
        finally:
            for task in (self.tts_task, self.turn_task):
                if task and not task.done():
                    task.cancel()
            tasks = [task for task in (self.tts_task, self.turn_task) if task]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


def build_live_voice_websocket(runtime: AgentRuntime) -> APIRouter:
    @router.websocket("/ws")
    async def live_voice(websocket: WebSocket) -> None:
        await websocket.accept()
        connection = LiveVoiceConnection(websocket, runtime)
        try:
            await connection.run()
        except (ValueError, KeyError, RuntimeError) as exc:
            try:
                await websocket.send_text(json.dumps({"type": "error", "stage": "protocol", "detail": str(exc)}))
            except Exception:
                pass

    return router
