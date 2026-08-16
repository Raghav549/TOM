from __future__ import annotations

import asyncio
import json
import os
import re
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tom.models import AgentRequest
from tom.runtime import AgentRuntime
from tom.voice.cosyvoice_stream import TTSChunk
from tom.voice.director import ConversationSignals
from tom.voice.live_commentary import LiveVoiceCommentary
from tom.voice.models import VOICE_PROFILES
from tom.voice.neural_vad import SileroStreamingVAD
from tom.voice.prosody_state import ContinuousProsodyTracker
from tom.voice.session import VoiceSession
from tom.voice.smart_turn_onnx import SmartTurnONNX
from tom.voice.streaming_asr import StreamingFasterWhisper
from tom.voice.tts_factory import build_streaming_tts
from tom.voice.turn_predictor import LearnedTurnPredictor
from tom.voice.turntaking import DuplexTurnManager, TurnSignal

router = APIRouter(prefix="/v1/voice", tags=["voice"])


def _next_or_none(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return None


class LiveVoiceConnection:
    """Continuous full-duplex voice transport with adaptive expressive TTS."""

    def __init__(self, websocket: WebSocket, runtime: AgentRuntime) -> None:
        self.websocket = websocket
        self.runtime = runtime
        self.asr = StreamingFasterWhisper()
        self.tts = build_streaming_tts()
        self.vad = SileroStreamingVAD()
        self.prosody = ContinuousProsodyTracker()
        self.turn_predictor = LearnedTurnPredictor()
        self.smart_turn = SmartTurnONNX()
        self.turns = DuplexTurnManager()
        self.conversation_id = str(uuid4())
        self.voice_id = "tom_m1"
        self.character_name = "TOM"
        self.character_style = "friendly+sigma"
        self.character_traits: tuple[str, ...] = ("helpful", "warm", "confident")
        self.character_pitch_shift: float | None = None
        self.character_speaking_rate: float | None = None
        self.character_warmth: float | None = None
        self.character_breathiness: float | None = None
        self.character_expressiveness: float | None = None
        self.audio_sample_rate = 16000
        self.turn_audio = bytearray()
        self.pending_audio = bytearray()
        self.pre_roll = bytearray()
        self.pre_roll_max = 320 * 2 * 16
        self.tom_speaking = False
        self.tts_task: asyncio.Task | None = None
        self.turn_task: asyncio.Task | None = None
        self.pending_tts_text: str | None = None
        self.pending_tts_index = 0
        self.awaiting_endpoint = False
        self.commentary: LiveVoiceCommentary | None = None
        self._last_vad = 0.0
        self._last_prosody_emit_ms = 0
        self._audio_ms = 0
        self._previous_vad = 0.0
        self._previous_energy = 0.0
        self._neural_vad = os.getenv("TOM_NEURAL_VAD", "1").lower() not in {"0", "false", "no"}

    async def send_event(self, event_type: str, **payload) -> None:
        await self.websocket.send_text(json.dumps({"type": event_type, **payload}, ensure_ascii=False))

    async def interrupt(self, reason: str = "user_barge_in") -> None:
        if self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
            await asyncio.gather(self.tts_task, return_exceptions=True)
        if self.commentary and self.commentary.task and not self.commentary.task.done():
            self.commentary.task.cancel()
            await asyncio.gather(self.commentary.task, return_exceptions=True)
        self.tts_task = None
        self.tom_speaking = False
        self.turns.update(
            TurnSignal(user_voice_active=True, user_voice_duration_ms=200, user_speech_confidence=0.95,
                       user_started_while_tom_speaking=True, explicit_interrupt=True),
            tom_speaking=True,
        )
        await self.send_event("audio_stop", reason=reason, cancelled=True, resumable=bool(self.pending_tts_text))

    def _signals(self, *, user_text: str, state) -> ConversationSignals:
        return ConversationSignals(
            user_text=user_text,
            user_is_excited=state.arousal >= 0.58,
            user_arousal=state.arousal,
            user_valence=state.valence_hint,
            character_name=self.character_name,
            character_style=self.character_style,
            character_traits=self.character_traits,
            character_pitch_shift=self.character_pitch_shift,
            character_speaking_rate=self.character_speaking_rate,
            character_warmth=self.character_warmth,
            character_breathiness=self.character_breathiness,
            character_expressiveness=self.character_expressiveness,
        )

    async def _speak_commentary(self, text: str) -> None:
        turn = VoiceSession(self.tts).prepare_turn(
            text,
            voice_id=self.voice_id,
            signals=ConversationSignals(
                user_text="",
                task_running=True,
                character_name=self.character_name,
                character_style=self.character_style,
                character_traits=self.character_traits,
                character_pitch_shift=self.character_pitch_shift,
                character_speaking_rate=self.character_speaking_rate,
                character_warmth=self.character_warmth,
                character_breathiness=self.character_breathiness,
                character_expressiveness=self.character_expressiveness,
            ),
        )
        self.tom_speaking = True
        try:
            await self.send_event("voice_state", value="commentary", text=text)
            iterator = self.tts.stream(text, language=turn.language, voice=VOICE_PROFILES[self.voice_id], style=turn.style)
            while True:
                chunk: TTSChunk | None = await asyncio.to_thread(_next_or_none, iterator)
                if chunk is None:
                    break
                await self.websocket.send_bytes(chunk.pcm16)
                await asyncio.sleep(0)
        finally:
            self.tom_speaking = False

    async def speak(self, text: str, *, voice_id: str | None = None,
                    signals: ConversationSignals | None = None, resume: bool = False) -> None:
        selected = voice_id or self.voice_id
        if selected not in VOICE_PROFILES:
            selected = "tom_m1"
        if not resume:
            self.pending_tts_text = text
            self.pending_tts_index = 0
        segments = [x.strip() for x in re.split(r"(?<=[.!?।])\s+", self.pending_tts_text or "") if x.strip()]
        remaining = " ".join(segments[self.pending_tts_index:])
        turn = VoiceSession(self.tts).prepare_turn(remaining, voice_id=selected, signals=signals)
        self.tom_speaking = True
        try:
            await self.send_event("audio_start", sample_rate=24000, channels=1, encoding="pcm_s16le",
                                  text=remaining, voice_id=selected, character_name=self.character_name,
                                  character_style=self.character_style, resumed=resume,
                                  tts_engine=os.getenv("TOM_TTS_ENGINE", "hybrid"),
                                  expressive=True, prosody_control=True, breath_timing=True)
            for index in range(self.pending_tts_index, len(segments)):
                self.pending_tts_index = index
                segment = segments[index]
                iterator = self.tts.stream(segment, language=turn.language, voice=VOICE_PROFILES[selected], style=turn.style)
                while True:
                    chunk: TTSChunk | None = await asyncio.to_thread(_next_or_none, iterator)
                    if chunk is None:
                        break
                    await self.websocket.send_bytes(chunk.pcm16)
                    await asyncio.sleep(0)
                self.pending_tts_index = index + 1
            self.pending_tts_text = None
            self.pending_tts_index = 0
        finally:
            self.tom_speaking = False
            await self.send_event("audio_end")

    async def _run_endpoint_model(self) -> bool:
        if not self.smart_turn.configured or not self.turn_audio:
            return True
        decision = await asyncio.to_thread(self.smart_turn.predict, bytes(self.turn_audio), 16000)
        await self.send_event("smart_turn", complete_probability=decision.complete_probability,
                              complete=decision.complete)
        return decision.complete

    async def _process_batch(self, pcm: bytes) -> None:
        self._audio_ms += int(len(pcm) / 2 * 1000 / self.audio_sample_rate)
        self.pre_roll.extend(pcm)
        if len(self.pre_roll) > self.pre_roll_max:
            del self.pre_roll[:-self.pre_roll_max]

        vad_decision = await asyncio.to_thread(self.vad.process, pcm, self.audio_sample_rate) if self._neural_vad else None
        state = await asyncio.to_thread(self.prosody.update, pcm, self.audio_sample_rate)
        self._last_vad = vad_decision.speech_probability if vad_decision else self._last_vad

        if self._audio_ms - self._last_prosody_emit_ms >= 160:
            self._last_prosody_emit_ms = self._audio_ms
            await self.send_event("prosody", continuous=True, pitch_hz=state.mean_pitch_hz,
                                  pitch_variation=state.pitch_variation, energy=state.energy,
                                  energy_variation=state.energy_variation, speech_rate=state.speech_rate,
                                  arousal=state.arousal, valence_hint=state.valence_hint,
                                  confidence=state.confidence, vad_probability=self._last_vad)

        partial = await asyncio.to_thread(self.asr.push, pcm, self.audio_sample_rate)
        if partial is not None and partial.text.strip():
            await self.send_event("partial_transcript", text=partial.text, confidence=partial.confidence, language=partial.language)

        if vad_decision and vad_decision.start:
            if self.tom_speaking:
                await self.interrupt("neural_vad_barge_in")
            if not self.awaiting_endpoint:
                self.turn_audio = bytearray(self.pre_roll)
                self.asr.reset()
                self.prosody.reset()
            else:
                self.awaiting_endpoint = False
            await self.send_event("state", value="listening")

        if vad_decision and vad_decision.speech:
            self.turn_audio.extend(pcm)

        if vad_decision and vad_decision.end and self.turn_audio:
            complete = await self._run_endpoint_model()
            if complete:
                if not self.turn_task or self.turn_task.done():
                    self.turn_task = asyncio.create_task(self.process_turn(bytes(self.turn_audio)))
                self.turn_audio.clear()
                self.awaiting_endpoint = False
            else:
                self.awaiting_endpoint = True
                await self.send_event("state", value="waiting_for_user_continuation")

        if self.turn_predictor.configured:
            prediction = await asyncio.to_thread(
                self.turn_predictor.predict,
                vad=self._last_vad, vad_delta=self._last_vad - self._previous_vad,
                energy=state.energy, energy_delta=state.energy - self._previous_energy,
                pitch_variation=state.pitch_variation, speech_rate=state.speech_rate,
                asr_confidence=partial.confidence if partial else 0.0, tom_speaking=self.tom_speaking,
            )
            self._previous_vad = self._last_vad
            self._previous_energy = state.energy
            await self.send_event("turn_prediction", end_probability=prediction.end_probability,
                                  interrupt_probability=prediction.interrupt_probability,
                                  continue_probability=prediction.continue_probability)
            if self.tom_speaking and prediction.interrupt_probability >= 0.72:
                await self.interrupt("learned_turn_interrupt")

    async def process_turn(self, pcm: bytes) -> None:
        if len(pcm) < 3200:
            return
        self.pending_tts_text = None
        self.pending_tts_index = 0
        await self.send_event("state", value="transcribing")
        try:
            self.asr.reset()
            self.asr._buffer.extend(pcm)
            final = await asyncio.to_thread(self.asr.final, self.audio_sample_rate)
        except RuntimeError as exc:
            await self.send_event("error", stage="asr", detail=str(exc))
            return
        text = final.text.strip()
        if not text:
            await self.send_event("state", value="listening")
            return
        state = self.prosody.state
        await self.send_event("transcript", text=text, confidence=final.confidence, language=final.language, final=True)
        await self.send_event("state", value="thinking")

        if self.commentary:
            await self.commentary.stop()
        self.commentary = LiveVoiceCommentary(
            self.runtime.events_bus,
            self.conversation_id,
            self._speak_commentary,
            self.send_event,
        )
        self.commentary.start()
        runtime_task = asyncio.create_task(self.runtime.handle(AgentRequest(
            message=text, conversation_id=self.conversation_id,
            context={"voice_turn": True, "asr_confidence": final.confidence,
                     "user_language": final.language, "user_pitch_hz": state.mean_pitch_hz,
                     "user_pitch_variation": state.pitch_variation, "user_energy": state.energy,
                     "user_arousal": state.arousal, "user_valence_hint": state.valence_hint,
                     "companion_name": self.character_name, "companion_style": self.character_style,
                     "companion_traits": list(self.character_traits)},
        )))
        try:
            response = await runtime_task
        finally:
            if self.commentary:
                await self.commentary.stop()
                self.commentary = None

        await self.send_event("response", text=response.reply, conversation_id=self.conversation_id,
                              character_name=self.character_name)
        self.tts_task = asyncio.create_task(self.speak(
            response.reply,
            signals=self._signals(user_text=text, state=state),
        ))
        try:
            await self.tts_task
        except asyncio.CancelledError:
            pass
        finally:
            self.tts_task = None

    @staticmethod
    def _clamp(value, low: float, high: float):
        if value is None:
            return None
        return max(low, min(high, float(value)))

    def _apply_character(self, payload: dict) -> None:
        character = payload.get("character") or {}
        if not isinstance(character, dict):
            character = {}
        self.character_name = str(character.get("name") or payload.get("name") or "TOM").strip()[:64] or "TOM"
        self.character_style = str(character.get("style") or payload.get("style") or "friendly+sigma").strip()[:64] or "friendly+sigma"
        traits = character.get("traits") or payload.get("traits") or ["helpful", "warm", "confident"]
        if isinstance(traits, str):
            traits = [traits]
        self.character_traits = tuple(str(item).strip()[:48] for item in traits if str(item).strip())[:12]
        self.character_pitch_shift = self._clamp(character.get("pitch_shift"), -1.0, 1.0)
        self.character_speaking_rate = self._clamp(character.get("speaking_rate"), 0.65, 1.35)
        self.character_warmth = self._clamp(character.get("warmth"), 0.0, 1.0)
        self.character_breathiness = self._clamp(character.get("breathiness"), 0.0, 1.0)
        self.character_expressiveness = self._clamp(character.get("expressiveness"), 0.0, 1.0)

    async def handle_text(self, message: str) -> None:
        payload = json.loads(message)
        event_type = payload.get("type", "")
        if event_type == "hello":
            self.voice_id = payload.get("voice_id", "tom_m1")
            self.audio_sample_rate = int(payload.get("sample_rate", 16000))
            self._apply_character(payload)
            await self.send_event("ready", protocol=3, conversation_id=self.conversation_id, sample_rate=24000,
                                  continuous_audio=True, neural_vad=self._neural_vad,
                                  learned_turn_prediction=self.turn_predictor.configured,
                                  smart_turn=self.smart_turn.configured,
                                  character={"name": self.character_name, "style": self.character_style,
                                             "traits": list(self.character_traits)},
                                  voice_capabilities=["emotion", "pitch", "rate", "warmth", "breath_timing",
                                                       "character_style", "voice_design", "barge_in", "resume",
                                                       "live_action_commentary"],
                                  default_character={"name": "TOM", "style": "friendly+sigma",
                                                     "traits": ["helpful", "warm", "confident"]})
        elif event_type == "set_character":
            self._apply_character(payload)
            await self.send_event("character_updated", name=self.character_name, style=self.character_style,
                                  traits=list(self.character_traits))
        elif event_type == "interrupt":
            await self.interrupt(payload.get("reason", "user_barge_in"))
        elif event_type == "audio_start":
            self.turn_audio.clear()
            self.awaiting_endpoint = False
            self.asr.reset()
            self.vad.reset()
            await self.send_event("state", value="listening")
        elif event_type == "audio_end":
            if self.turn_audio and (not self.turn_task or self.turn_task.done()):
                self.turn_task = asyncio.create_task(self.process_turn(bytes(self.turn_audio)))
                self.turn_audio.clear()
        elif event_type == "resume_audio":
            if self.pending_tts_text and self.pending_tts_index < len(re.split(r"(?<=[.!?।])\s+", self.pending_tts_text)):
                self.tts_task = asyncio.create_task(self.speak(self.pending_tts_text, resume=True))
            else:
                await self.send_event("resume", supported=False, reason="no resumable TTS segment")

    async def run(self) -> None:
        await self.send_event("connected", protocol=3)
        try:
            while True:
                message = await self.websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    await self.handle_text(message["text"])
                elif message.get("bytes") is not None:
                    self.pending_audio.extend(message["bytes"])
                    frame_bytes = 320 * 2
                    while len(self.pending_audio) >= frame_bytes:
                        frame = bytes(self.pending_audio[:frame_bytes])
                        del self.pending_audio[:frame_bytes]
                        await self._process_batch(frame)
        except WebSocketDisconnect:
            return
        finally:
            if self.commentary:
                await self.commentary.stop()
                self.commentary = None
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
            await websocket.send_text(json.dumps({"type": "error", "stage": "protocol", "detail": str(exc)}))

    return router
