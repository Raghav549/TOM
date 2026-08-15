from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tom.models import AgentRequest
from tom.runtime import AgentRuntime
from tom.voice.asr import FasterWhisperASR
from tom.voice.cosyvoice_stream import CosyVoiceStreamingAdapter, TTSChunk
from tom.voice.director import ConversationSignals
from tom.voice.models import VOICE_PROFILES
from tom.voice.prosody import PCM16ProsodyExtractor
from tom.voice.session import VoiceSession
from tom.voice.turntaking import DuplexTurnManager, TurnSignal

router = APIRouter(prefix="/v1/voice", tags=["voice"])


def _next_or_none(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return None


class LiveVoiceConnection:
    """Full-duplex Core-side voice session.

    Android sends 16 kHz mono PCM16 speech frames. TOM transcribes completed
    turns, runs the existing agent runtime, and streams real TTS PCM16 back.
    The receive loop stays live while ASR/LLM/TTS work runs in tasks, so a
    barge-in can reach the cancellation path immediately.
    """

    def __init__(self, websocket: WebSocket, runtime: AgentRuntime) -> None:
        self.websocket = websocket
        self.runtime = runtime
        self.asr = FasterWhisperASR()
        self.tts = CosyVoiceStreamingAdapter()
        self.prosody = PCM16ProsodyExtractor()
        self.turns = DuplexTurnManager()
        self.conversation_id = str(uuid4())
        self.audio = bytearray()
        self.audio_sample_rate = 16000
        self.tts_task: asyncio.Task | None = None
        self.turn_task: asyncio.Task | None = None
        self.tom_speaking = False
        self.voice_id = "tom_m1"

    async def send_event(self, event_type: str, **payload) -> None:
        await self.websocket.send_text(
            json.dumps({"type": event_type, **payload}, ensure_ascii=False)
        )

    async def interrupt(self, reason: str = "user_barge_in") -> None:
        if self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
            await asyncio.gather(self.tts_task, return_exceptions=True)
        self.tts_task = None
        self.tom_speaking = False
        self.turns.update(
            TurnSignal(
                user_voice_active=True,
                user_voice_duration_ms=200,
                user_speech_confidence=0.95,
                user_started_while_tom_speaking=True,
                explicit_interrupt=True,
            ),
            tom_speaking=True,
        )
        await self.send_event("audio_stop", reason=reason)

    async def speak(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        signals: ConversationSignals | None = None,
    ) -> None:
        selected = voice_id or self.voice_id
        if selected not in VOICE_PROFILES:
            selected = "tom_m1"
        turn = VoiceSession(self.tts).prepare_turn(text, voice_id=selected, signals=signals)
        await self.send_event(
            "audio_start",
            sample_rate=24000,
            channels=1,
            encoding="pcm_s16le",
            text=text,
            voice_id=selected,
        )
        self.tom_speaking = True
        iterator = self.tts.stream(
            turn.text,
            language=turn.language,
            voice=VOICE_PROFILES[selected],
            style=turn.style,
        )
        try:
            while True:
                chunk: TTSChunk | None = await asyncio.to_thread(_next_or_none, iterator)
                if chunk is None:
                    break
                await self.websocket.send_bytes(chunk.pcm16)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        finally:
            self.tom_speaking = False
            await self.send_event("audio_end")

    async def process_turn(self) -> None:
        pcm = bytes(self.audio)
        self.audio.clear()
        if len(pcm) < 3200:
            return
        await self.send_event("state", value="transcribing")
        try:
            text, asr_confidence, language = await asyncio.to_thread(
                self.asr.transcribe, pcm, self.audio_sample_rate
            )
        except RuntimeError as exc:
            await self.send_event("error", stage="asr", detail=str(exc))
            return
        if not text.strip():
            await self.send_event("state", value="listening")
            return

        user_prosody = await asyncio.to_thread(
            self.prosody.analyze, pcm, self.audio_sample_rate
        )
        await self.send_event(
            "transcript",
            text=text,
            confidence=asr_confidence,
            language=language,
            prosody={
                "mean_pitch_hz": user_prosody.mean_pitch_hz,
                "pitch_range_hz": user_prosody.pitch_range_hz,
                "energy": user_prosody.energy,
                "energy_variation": user_prosody.energy_variation,
                "pitch_variation": user_prosody.pitch_variation,
                "speech_rate_proxy": user_prosody.speech_rate_proxy,
                "likely_excited": user_prosody.likely_excited,
                "likely_tired_or_calm": user_prosody.likely_tired_or_calm,
            },
        )

        await self.send_event("state", value="thinking")
        response = await self.runtime.handle(
            AgentRequest(
                message=text,
                conversation_id=self.conversation_id,
                context={
                    "voice_turn": True,
                    "asr_confidence": asr_confidence,
                    "user_language": language,
                    "user_pitch_hz": user_prosody.mean_pitch_hz,
                    "user_pitch_variation": user_prosody.pitch_variation,
                    "user_energy": user_prosody.energy,
                    "user_arousal_hint": user_prosody.likely_excited,
                },
            )
        )
        await self.send_event("response", text=response.reply, conversation_id=self.conversation_id)

        self.tts_task = asyncio.create_task(
            self.speak(
                response.reply,
                signals=ConversationSignals(
                    user_text=text,
                    user_is_excited=user_prosody.likely_excited,
                    user_arousal=user_prosody.pitch_variation,
                ),
            )
        )
        try:
            await self.tts_task
        except asyncio.CancelledError:
            pass
        finally:
            self.tts_task = None

    async def handle_text(self, message: str) -> None:
        payload = json.loads(message)
        event_type = payload.get("type", "")
        if event_type == "hello":
            self.voice_id = payload.get("voice_id", "tom_m1")
            self.audio_sample_rate = int(payload.get("sample_rate", 16000))
            await self.send_event(
                "ready",
                protocol=1,
                conversation_id=self.conversation_id,
                sample_rate=24000,
            )
        elif event_type == "audio_start":
            self.audio.clear()
            self.audio_sample_rate = int(payload.get("sample_rate", 16000))
            self.turns.update(
                TurnSignal(user_voice_active=True, user_voice_duration_ms=1, user_speech_confidence=0.8),
                tom_speaking=self.tom_speaking,
            )
        elif event_type == "interrupt":
            await self.interrupt(payload.get("reason", "user_barge_in"))
        elif event_type == "audio_end":
            self.turns.update(
                TurnSignal(user_voice_active=False, user_stopped_ms_ago=500),
                tom_speaking=self.tom_speaking,
            )
            if self.turn_task and not self.turn_task.done():
                await self.send_event("state", value="busy")
                self.audio.clear()
            else:
                self.turn_task = asyncio.create_task(self.process_turn())

    async def run(self) -> None:
        await self.send_event("connected", protocol=1)
        try:
            while True:
                message = await self.websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    await self.handle_text(message["text"])
                elif message.get("bytes") is not None:
                    self.audio.extend(message["bytes"])
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
            await websocket.send_text(
                json.dumps({"type": "error", "stage": "protocol", "detail": str(exc)})
            )

    return router
