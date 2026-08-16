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
    """Low-latency full-duplex voice transport.

    The hot path is deliberately overlapped:
    microphone -> VAD/prosody/partial-ASR -> turn decision -> LLM stream ->
    phrase boundary -> Qwen/streaming TTS -> PCM playback.

    Consequential tools never execute from speculative partial ASR. Tool turns
    remain on AgentRuntime's normal verified path; only the conversational
    response text is streamed early.
    """

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
        self._last_vad = 0.0
        self._last_prosody_emit_ms = 0
        self._audio_ms = 0
        self._previous_vad = 0.0
        self._previous_energy = 0.0
        self._neural_vad = os.getenv("TOM_NEURAL_VAD", "1").lower() not in {"0", "false", "no"}
        self._latency = {}
        self._response_buffer = ""

    async def send_event(self, event_type: str, **payload) -> None:
        await self.websocket.send_text(json.dumps({"type": event_type, **payload}, ensure_ascii=False))

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
            await self.send_event(
                "audio_start", sample_rate=24000, channels=1, encoding="pcm_s16le", text=remaining,
                voice_id=selected, character_name=self.character_name, character_style=self.character_style,
                resumed=resume, tts_engine=os.getenv("TOM_TTS_ENGINE", "hybrid"), expressive=True,
                prosody_control=True, breath_timing=True,
            )
            for index in range(self.pending_tts_index, len(segments)):
                self.pending_tts_index = index
                iterator = self.tts.stream(segments[index], language=turn.language, voice=VOICE_PROFILES[selected], style=turn.style)
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

    @staticmethod
    def _phrase_boundary(buffer: str, *, final: bool = False) -> tuple[str, str]:
        """Return (ready_phrase, remainder) without cutting words.

        Strong punctuation is preferred. For natural low-latency speech a soft
        clause boundary is allowed once enough text exists, so Qwen does not
        wait for an entire paragraph before producing the first sound.
        """
        text = buffer.strip()
        if not text:
            return "", ""
        strong = re.search(r"^(.{18,}?[.!?।])(?:\s+|$)", text, re.S)
        if strong:
            return strong.group(1).strip(), text[strong.end():].strip()
        clause = re.search(r"^(.{28,80}?[,:;])\s+", text, re.S)
        if clause:
            return clause.group(1).strip(), text[clause.end():].strip()
        if final:
            return text, ""
        return "", text

    async def _stream_response_audio(self, response_stream, *, user_text: str, state) -> str:
        """Consume LLM deltas while a TTS worker speaks completed phrases."""
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=3)
        full_response: list[str] = []
        buffer = ""
        first_audio_sent = False
        tts_started_at = time.perf_counter()
        signals = self._signals(user_text=user_text, state=state)
        selected = self.voice_id if self.voice_id in VOICE_PROFILES else "tom_m1"

        async def tts_worker() -> None:
            nonlocal first_audio_sent
            while True:
                phrase = await queue.get()
                if phrase is None:
                    return
                phrase = phrase.strip()
                if not phrase:
                    continue
                turn = VoiceSession(self.tts).prepare_turn(phrase, voice_id=selected, signals=signals)
                iterator = self.tts.stream(phrase, language=turn.language, voice=VOICE_PROFILES[selected], style=turn.style)
                while True:
                    chunk: TTSChunk | None = await asyncio.to_thread(_next_or_none, iterator)
                    if chunk is None:
                        break
                    if not first_audio_sent:
                        first_audio_sent = True
                        self._latency["tts_first_audio_ms"] = round((time.perf_counter() - tts_started_at) * 1000, 1)
                        await self.send_event("latency", **self._latency)
                    await self.websocket.send_bytes(chunk.pcm16)
                    await asyncio.sleep(0)

        worker = asyncio.create_task(tts_worker())
        self.tom_speaking = True
        await self.send_event(
            "audio_start", sample_rate=24000, channels=1, encoding="pcm_s16le", voice_id=selected,
            character_name=self.character_name, character_style=self.character_style,
            tts_engine=os.getenv("TOM_TTS_ENGINE", "hybrid"), streaming=True, expressive=True,
            prosody_control=True, breath_timing=True,
        )
        try:
            async for token in response_stream:
                if not token:
                    continue
                full_response.append(token)
                buffer += token
                self._response_buffer = "".join(full_response)
                await self.send_event("response_partial", text=token)
                phrase, buffer = self._phrase_boundary(buffer)
                if phrase:
                    await queue.put(phrase)
            phrase, buffer = self._phrase_boundary(buffer, final=True)
            if phrase:
                await queue.put(phrase)
            await queue.put(None)
            await worker
        finally:
            if not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
            self.tom_speaking = False
            await self.send_event("audio_end")
        return "".join(full_response).strip()

    async def _run_endpoint_model(self) -> bool:
        if not self.smart_turn.configured or not self.turn_audio:
            return True
        decision = await asyncio.to_thread(self.smart_turn.predict, bytes(self.turn_audio), 16000)
        await self.send_event("smart_turn", complete_probability=decision.complete_probability, complete=decision.complete)
        return decision.complete

    async def _process_batch(self, pcm: bytes) -> None:
        self._audio_ms += int(len(pcm) / 2 * 1000 / self.audio_sample_rate)
        self.pre_roll.extend(pcm)
        if len(self.pre_roll) > self.pre_roll_max:
            del self.pre_roll[:-self.pre_roll_max]

        # These are independent observations over the same frame. Run them in
        # parallel so ASR inference never blocks VAD or continuous prosody.
        vad_task = asyncio.to_thread(self.vad.process, pcm, self.audio_sample_rate) if self._neural_vad else None
        prosody_task = asyncio.to_thread(self.prosody.update, pcm, self.audio_sample_rate)
        asr_task = asyncio.to_thread(self.asr.push, pcm, self.audio_sample_rate)
        if vad_task is not None:
            vad_decision, state, partial = await asyncio.gather(vad_task, prosody_task, asr_task)
        else:
            state, partial = await asyncio.gather(prosody_task, asr_task)
            vad_decision = None

        self._last_vad = vad_decision.speech_probability if vad_decision else self._last_vad
        if self._audio_ms - self._last_prosody_emit_ms >= 160:
            self._last_prosody_emit_ms = self._audio_ms
            await self.send_event(
                "prosody", continuous=True, pitch_hz=state.mean_pitch_hz, pitch_variation=state.pitch_variation,
                energy=state.energy, energy_variation=state.energy_variation, speech_rate=state.speech_rate,
                arousal=state.arousal, valence_hint=state.valence_hint, confidence=state.confidence,
                vad_probability=self._last_vad,
            )

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
                vad=self._last_vad,
                vad_delta=self._last_vad - self._previous_vad,
                energy=state.energy,
                energy_delta=state.energy - self._previous_energy,
                pitch_variation=state.pitch_variation,
                speech_rate=state.speech_rate,
                asr_confidence=partial.confidence if partial else 0.0,
                tom_speaking=self.tom_speaking,
            )
            self._previous_vad = self._last_vad
            self._previous_energy = state.energy
            await self.send_event(
                "turn_prediction", end_probability=prediction.end_probability,
                interrupt_probability=prediction.interrupt_probability,
                continue_probability=prediction.continue_probability,
            )
            if self.tom_speaking and prediction.interrupt_probability >= 0.72:
                await self.interrupt("learned_turn_interrupt")

    async def process_turn(self, pcm: bytes) -> None:
        if len(pcm) < 3200:
            return
        self.pending_tts_text = None
        self.pending_tts_index = 0
        self._latency = {"turn_started_at_ms": round(time.time() * 1000)}
        await self.send_event("state", value="transcribing")
        try:
            self.asr.reset()
            self.asr._buffer.extend(pcm)
            final = await asyncio.to_thread(self.asr.final, self.audio_sample_rate)
        except RuntimeError as exc:
            await self.send_event("error", stage="asr", detail=str(exc))
            return
        text = final.text.strip()
        self._latency["final_asr_ms"] = round(time.time() * 1000 - self._latency["turn_started_at_ms"], 1)
        if not text:
            await self.send_event("state", value="listening")
            return

        state = self.prosody.state
        await self.send_event("transcript", text=text, confidence=final.confidence, language=final.language, final=True)
        await self.send_event("state", value="thinking")
        self._latency["llm_start_ms"] = round(time.time() * 1000, 1)

        request = AgentRequest(
            message=text,
            conversation_id=self.conversation_id,
            context={
                "voice_turn": True,
                "asr_confidence": final.confidence,
                "user_language": final.language,
                "user_pitch_hz": state.mean_pitch_hz,
                "user_pitch_variation": state.pitch_variation,
                "user_energy": state.energy,
                "user_arousal": state.arousal,
                "user_valence_hint": state.valence_hint,
                "companion_name": self.character_name,
                "companion_style": self.character_style,
                "companion_traits": list(self.character_traits),
            },
        )

        response_stream = self.runtime.stream_conversational_response(request)
        self.tts_task = asyncio.create_task(self._stream_response_audio(response_stream, user_text=text, state=state))
        try:
            response_text = await self.tts_task
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 - provider boundaries
            await self.send_event("error", stage="voice_pipeline", detail=str(exc))
            return
        finally:
            self.tts_task = None

        if not response_text:
            await self.send_event("state", value="listening")
            return
        self.pending_tts_text = response_text
        self.pending_tts_index = 0
        self._latency["response_complete_ms"] = round(time.time() * 1000, 1)
        await self.send_event(
            "response", text=response_text, conversation_id=self.conversation_id,
            character_name=self.character_name, streaming=True, latency=self._latency,
        )
        await self.send_event("state", value="listening")

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
            if self.audio_sample_rate != 16000:
                raise ValueError("voice websocket input must be 16 kHz PCM16")
            self._apply_character(payload)
            await self.send_event(
                "ready", protocol=4, conversation_id=self.conversation_id, sample_rate=24000,
                continuous_audio=True, neural_vad=self._neural_vad,
                learned_turn_prediction=self.turn_predictor.configured,
                smart_turn=self.smart_turn.configured,
                overlapped_pipeline=True,
                character={"name": self.character_name, "style": self.character_style, "traits": list(self.character_traits)},
                voice_capabilities=[
                    "emotion", "pitch", "rate", "warmth", "breath_timing", "character_style", "voice_design",
                    "barge_in", "resume", "partial_asr", "llm_token_stream", "phrase_tts", "full_duplex",
                ],
                default_character={"name": "TOM", "style": "friendly+sigma", "traits": ["helpful", "warm", "confident"]},
            )
        elif event_type == "set_character":
            self._apply_character(payload)
            await self.send_event("character_updated", name=self.character_name, style=self.character_style, traits=list(self.character_traits))
        elif event_type == "interrupt":
            await self.interrupt(payload.get("reason", "user_barge_in"))
        elif event_type == "audio_start":
            self.turn_audio.clear()
            self.awaiting_endpoint = False
            self.asr.reset()
            self.vad.reset()
            self.prosody.reset()
            await self.send_event("state", value="listening")
        elif event_type == "audio_end":
            if self.turn_audio and (not self.turn_task or self.turn_task.done()):
                self.turn_task = asyncio.create_task(self.process_turn(bytes(self.turn_audio)))
                self.turn_audio.clear()
        elif event_type == "resume_audio":
            if self.pending_tts_text:
                self.tts_task = asyncio.create_task(self.speak(self.pending_tts_text, resume=True))
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
                    frame_bytes = 320 * 2
                    while len(self.pending_audio) >= frame_bytes:
                        frame = bytes(self.pending_audio[:frame_bytes])
                        del self.pending_audio[:frame_bytes]
                        await self._process_batch(frame)
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
            await websocket.send_text(json.dumps({"type": "error", "stage": "protocol", "detail": str(exc)}))

    return router
