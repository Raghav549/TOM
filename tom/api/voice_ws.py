from __future__ import annotations

import asyncio
import json
import logging
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
from tom.voice.prosody_state import ContinuousProsodyTracker
from tom.voice.session import VoiceSession
from tom.voice.streaming_asr import StreamingFasterWhisper
from tom.voice.tts_factory import build_streaming_tts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/voice", tags=["voice"])

_SENTENCE_END = re.compile(r"[.!?।]+[\"'”’)]*(?=\s|$)")
_SOFT_BREAK = re.compile(r"[,;:—–-](?=\s)")
_END_OF_QUEUE = None


def _next_or_none(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return None


def _rms_threshold() -> float:
    """Return the speech RMS threshold for 16-bit PCM.

    ``TOM_VOICE_RMS_THRESHOLD`` is the explicit RMS knob. For backwards
    compatibility a ``TOM_VAD_THRESHOLD`` value in the ``0..1`` range (the neural
    VAD probability scale used elsewhere) is mapped onto the same RMS scale that
    :func:`_simple_vad` uses for its probability estimate.
    """
    explicit = os.getenv("TOM_VOICE_RMS_THRESHOLD", "").strip()
    if explicit:
        try:
            return max(1.0, float(explicit))
        except ValueError:
            logger.warning("Ignoring invalid TOM_VOICE_RMS_THRESHOLD=%r", explicit)
    legacy = os.getenv("TOM_VAD_THRESHOLD", "").strip()
    if legacy:
        try:
            value = float(legacy)
        except ValueError:
            logger.warning("Ignoring invalid TOM_VAD_THRESHOLD=%r", legacy)
        else:
            if 0.0 < value <= 1.0:
                return value * 2000.0
            if value > 1.0:
                return value
    return 180.0


def _simple_vad(pcm: bytes, threshold: float = 180.0) -> tuple[float, bool, float]:
    """Energy VAD for 16 kHz PCM16 frames: ``(probability, is_speech, rms)``."""
    if not pcm:
        return 0.0, False, 0.0
    try:
        import numpy as np
    except ImportError:
        return 0.0, False, 0.0
    audio = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype=np.int16).astype(np.float32)
    if audio.size == 0:
        return 0.0, False, 0.0
    rms = float(np.sqrt(np.mean(audio * audio)))
    probability = min(1.0, rms / 2000.0)
    return probability, rms >= threshold, rms


class LiveVoiceConnection:
    """Production voice transport for Android 16 kHz PCM16 audio.

    Uses a lightweight CPU-safe VAD on Render, then ASR -> LLM -> Qwen TTS.
    The client can also explicitly delimit a turn with audio_start/audio_end,
    so a conservative VAD never becomes a silent failure mode.

    LLM tokens are streamed and spoken phrase-by-phrase: the first sentence is
    handed to TTS while the model is still generating the rest of the reply.
    """

    MIN_TURN_BYTES = 6400  # 200 ms at 16 kHz PCM16
    FRAME_BYTES = 640  # 20 ms at 16 kHz PCM16
    FRAME_MS = 20
    SILENCE_END_MS = 700
    MIN_SPEECH_MS = 200
    PARTIAL_INTERVAL_MS = 800

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
        self.explicit_turn = False
        self.silence_ms = 0
        self.speech_ms = 0
        self.last_partial_at_ms = 0
        self.last_audio_log_ms = 0
        self.last_vad_probability = 0.0
        self.last_rms = 0.0
        self.rms_threshold = _rms_threshold()
        self.tts_task: asyncio.Task | None = None
        self.turn_task: asyncio.Task | None = None
        self.pending_tts_text: str | None = None
        self.tom_speaking = False
        self.closed = False
        self._latency: dict[str, float] = {}

    # ------------------------------------------------------------------ transport

    async def send_event(self, event_type: str, **payload) -> None:
        if self.closed:
            return
        try:
            await self.websocket.send_text(json.dumps({"type": event_type, **payload}, ensure_ascii=False))
        except (WebSocketDisconnect, RuntimeError) as exc:
            # Starlette raises RuntimeError once the socket is closed.
            self.closed = True
            logger.debug("voice websocket closed while sending %s: %s", event_type, exc)

    async def send_audio(self, pcm16: bytes) -> bool:
        if self.closed or not pcm16:
            return False
        try:
            await self.websocket.send_bytes(pcm16)
        except (WebSocketDisconnect, RuntimeError) as exc:
            self.closed = True
            logger.debug("voice websocket closed while streaming audio: %s", exc)
            return False
        return True

    # ------------------------------------------------------------------ speech out

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

    @staticmethod
    def _phrase_boundary(text: str, *, min_chars: int = 24, max_chars: int = 160) -> tuple[str, str]:
        """Split ``text`` into ``(speakable_phrase, remainder)``.

        Prefers a sentence terminator once at least ``min_chars`` are buffered,
        falls back to a soft punctuation break and finally to a word boundary when
        the buffer grows past ``max_chars``. Returns ``("", text)`` when the buffer
        is not yet worth speaking. Words are never cut in half.
        """
        stripped = text.lstrip()
        if not stripped:
            return "", ""
        for match in _SENTENCE_END.finditer(stripped):
            end = match.end()
            # Very short sentences ("Ok.", "Haan.") are merged with the next
            # phrase so TTS gets natural prosody instead of clipped fragments.
            if end >= min_chars:
                return stripped[:end].strip(), stripped[end:].lstrip()
        if len(stripped) < max_chars:
            return "", stripped
        window = stripped[:max_chars]
        soft = [m.end() for m in _SOFT_BREAK.finditer(window) if m.end() >= min_chars]
        if soft:
            cut = soft[-1]
            return window[:cut].strip(), stripped[cut:].lstrip()
        space = window.rfind(" ")
        if space >= min_chars:
            return window[:space].strip(), stripped[space:].lstrip()
        return "", stripped

    def _synthesize_phrase(self, phrase: str, selected: str):
        signals = self._signals(user_text="")
        turn = VoiceSession(self.tts).prepare_turn(phrase, voice_id=selected, signals=signals)
        return self.tts.stream(phrase, language=turn.language, voice=VOICE_PROFILES[selected], style=turn.style)

    async def _speak_phrases(self, phrases: asyncio.Queue[str | None]) -> None:
        """Stream TTS audio for phrases as they arrive.

        Emits ``audio_start`` before the first PCM frame and ``audio_end`` after the
        last one. On cancellation (barge-in) the unspoken remainder is kept in
        ``pending_tts_text`` so ``resume_audio`` can continue where TOM stopped.
        """
        selected = self.voice_id if self.voice_id in VOICE_PROFILES else "tom_m1"
        started = False
        current: str | None = None
        try:
            while True:
                current = await phrases.get()
                if current is _END_OF_QUEUE:
                    break
                if not current or not current.strip():
                    continue
                if not started:
                    started = True
                    self.tom_speaking = True
                    self.pending_tts_text = None
                    await self.send_event("audio_start", sample_rate=24000, channels=1, encoding="pcm_s16le", voice_id=selected, streaming=True)
                try:
                    iterator = await asyncio.to_thread(self._synthesize_phrase, current, selected)
                    while True:
                        chunk: TTSChunk | None = await asyncio.to_thread(_next_or_none, iterator)
                        if chunk is None:
                            break
                        if not await self.send_audio(chunk.pcm16):
                            return
                        await asyncio.sleep(0)
                except (RuntimeError, ValueError) as exc:
                    # Unsupported language / TTS host down: report the exact stage
                    # so the phone can fall back to its own TTS for the text reply.
                    logger.warning("TTS failed for phrase: %s", exc)
                    await self.send_event("error", stage="tts", detail=str(exc))
                    return
                current = None
        except asyncio.CancelledError:
            remainder = [current] if current else []
            while not phrases.empty():
                item = phrases.get_nowait()
                if item:
                    remainder.append(item)
            self.pending_tts_text = " ".join(x.strip() for x in remainder if x and x.strip()) or None
            raise
        finally:
            self.tom_speaking = False
            if started:
                await self.send_event("audio_end")

    async def _speak(self, text: str) -> None:
        """Speak a complete text (used by resume_audio)."""
        text = text.strip()
        if not text:
            return
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        remaining = text
        while remaining:
            phrase, rest = self._phrase_boundary(remaining)
            if not phrase:
                phrase, rest = remaining, ""
            queue.put_nowait(phrase)
            remaining = rest
        queue.put_nowait(_END_OF_QUEUE)
        await self._speak_phrases(queue)

    # ------------------------------------------------------------------ turn handling

    async def process_turn(self, pcm: bytes) -> None:
        if len(pcm) < self.MIN_TURN_BYTES:
            await self.send_event("error", stage="asr", detail="audio_turn_too_short")
            await self.send_event("state", value="listening")
            return
        await self.send_event("state", value="transcribing")
        started = time.monotonic()
        self.asr.load(pcm, 16000)
        try:
            final = await asyncio.to_thread(self.asr.final, 16000)
        except Exception as exc:  # noqa: BLE001 - model errors must surface to the client, not kill the socket
            logger.exception("ASR final transcription failed")
            await self.send_event("error", stage="asr", detail=str(exc))
            await self.send_event("state", value="listening")
            return
        self._latency["asr_ms"] = round((time.monotonic() - started) * 1000)
        text = final.text.strip()
        if not text:
            await self.send_event("error", stage="asr", detail="no_speech_transcript")
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
        phrases: asyncio.Queue[str | None] = asyncio.Queue()
        self.tts_task = asyncio.create_task(self._speak_phrases(phrases))
        first_token_at: float | None = None
        try:
            response_parts: list[str] = []
            buffer = ""
            async for token in self.runtime.stream_conversational_response(request):
                if not token:
                    continue
                if first_token_at is None:
                    first_token_at = time.monotonic()
                    self._latency["llm_first_token_ms"] = round((first_token_at - started) * 1000)
                response_parts.append(token)
                buffer += token
                await self.send_event("response_partial", text=token)
                while True:
                    phrase, rest = self._phrase_boundary(buffer)
                    if not phrase:
                        break
                    buffer = rest
                    phrases.put_nowait(phrase)
            if buffer.strip():
                phrases.put_nowait(buffer.strip())
            response = "".join(response_parts).strip()
            if not response:
                raise RuntimeError("LLM returned an empty response")
            await self.send_event("response", text=response, conversation_id=self.conversation_id, streaming=True, latency=dict(self._latency))
            phrases.put_nowait(_END_OF_QUEUE)
            await self.tts_task
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the socket alive and report the stage that failed
            logger.exception("voice pipeline failed")
            phrases.put_nowait(_END_OF_QUEUE)
            if self.tts_task and not self.tts_task.done():
                self.tts_task.cancel()
                await asyncio.gather(self.tts_task, return_exceptions=True)
            await self.send_event("error", stage="voice_pipeline", detail=str(exc))
        finally:
            self.tts_task = None
            await self.send_event("state", value="listening")

    async def _emit_partial(self, pcm: bytes, now_ms: int) -> None:
        if now_ms - self.last_partial_at_ms < self.PARTIAL_INTERVAL_MS:
            return
        self.last_partial_at_ms = now_ms
        try:
            partial = await asyncio.to_thread(self.asr.push, pcm, 16000)
        except Exception as exc:  # noqa: BLE001 - partials are best-effort; the final pass reports hard failures
            logger.debug("partial ASR failed: %s", exc)
            await self.send_event("error", stage="partial_asr", detail=str(exc))
            return
        if partial and partial.text.strip():
            await self.send_event("partial_transcript", text=partial.text, confidence=partial.confidence, language=partial.language)

    def _start_turn_task(self, turn: bytes) -> None:
        if self.turn_task and not self.turn_task.done():
            logger.info("dropping voice turn: previous turn still processing")
            return
        self.turn_task = asyncio.create_task(self.process_turn(turn))

    async def _process_frame(self, pcm: bytes) -> None:
        if not pcm:
            return
        self.pre_roll.extend(pcm)
        if len(self.pre_roll) > self.pre_roll_max:
            del self.pre_roll[:-self.pre_roll_max]
        try:
            state = await asyncio.to_thread(self.prosody.update, pcm, 16000)
        except Exception as exc:  # noqa: BLE001 - prosody is advisory; never block audio on it
            logger.debug("prosody update failed: %s", exc)
            state = self.prosody.state
        probability, speech, rms = _simple_vad(pcm, self.rms_threshold)
        self.last_vad_probability = probability
        self.last_rms = rms
        now_ms = int(time.time() * 1000)
        if now_ms - self.last_audio_log_ms >= 2000:
            self.last_audio_log_ms = now_ms
            await self.send_event("audio_debug", rms=round(rms, 1), vad_probability=round(probability, 3), speech=bool(speech), explicit_turn=self.explicit_turn, threshold=self.rms_threshold)

        if self.explicit_turn:
            self.turn_audio.extend(pcm)
            await self._emit_partial(pcm, now_ms)
            return

        if speech:
            if not self.in_speech:
                self.in_speech = True
                self.silence_ms = 0
                self.speech_ms = 0
                self.turn_audio = bytearray(self.pre_roll)
                self.asr.reset()
                await self.send_event("state", value="listening")
            self.speech_ms += self.FRAME_MS
            self.silence_ms = 0
            self.turn_audio.extend(pcm)
            await self._emit_partial(pcm, now_ms)
        elif self.in_speech:
            self.silence_ms += self.FRAME_MS
            self.turn_audio.extend(pcm)
            if self.silence_ms >= self.SILENCE_END_MS and self.speech_ms >= self.MIN_SPEECH_MS:
                self.in_speech = False
                turn = bytes(self.turn_audio)
                self.turn_audio.clear()
                self.silence_ms = 0
                self.speech_ms = 0
                self._start_turn_task(turn)
        if now_ms % 1000 < 30:
            await self.send_event("prosody", continuous=True, energy=state.energy, arousal=state.arousal, valence_hint=state.valence_hint, vad_probability=probability)

    # ------------------------------------------------------------------ control messages

    def _apply_character(self, character: dict) -> None:
        self.character_name = str(character.get("name") or self.character_name).strip()[:64] or "TOM"
        self.character_style = str(character.get("style") or self.character_style).strip()[:64] or "friendly+sigma"
        traits = character.get("traits") or self.character_traits
        if isinstance(traits, str):
            traits = [traits]
        self.character_traits = tuple(str(x).strip()[:48] for x in traits if str(x).strip())[:12] or self.character_traits

    async def _cancel_speech(self, reason: str) -> None:
        if self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
            await asyncio.gather(self.tts_task, return_exceptions=True)
            self.tts_task = None
        self.tom_speaking = False
        await self.send_event("audio_stop", reason=reason, cancelled=True, resumable=bool(self.pending_tts_text))

    async def handle_text(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            await self.send_event("error", stage="protocol", detail="invalid_json")
            return
        if not isinstance(payload, dict):
            await self.send_event("error", stage="protocol", detail="message_must_be_object")
            return
        event_type = str(payload.get("type", ""))
        if event_type == "hello":
            requested_voice = str(payload.get("voice_id") or "tom_m1")
            self.voice_id = requested_voice if requested_voice in VOICE_PROFILES else "tom_m1"
            try:
                self.audio_sample_rate = int(payload.get("sample_rate", 16000))
            except (TypeError, ValueError):
                self.audio_sample_rate = 0
            if self.audio_sample_rate != 16000:
                await self.send_event("error", stage="protocol", detail="voice websocket input must be 16 kHz PCM16")
                return
            character = payload.get("character") or {}
            if isinstance(character, dict):
                self._apply_character(character)
            await self.send_event(
                "ready",
                protocol=4,
                conversation_id=self.conversation_id,
                sample_rate=24000,
                voice_id=self.voice_id,
                continuous_audio=True,
                neural_vad=False,
                lightweight_vad=True,
                explicit_turn_control=True,
                full_duplex=True,
                tts_engine=os.getenv("TOM_TTS_ENGINE", "qwen3"),
            )
        elif event_type == "set_character":
            character = payload.get("character") or payload
            if isinstance(character, dict):
                self._apply_character(character)
            await self.send_event("character_updated", name=self.character_name, style=self.character_style, traits=list(self.character_traits))
        elif event_type == "audio_start":
            if self.tom_speaking:
                # The user started talking over TOM: treat it as barge-in.
                await self._cancel_speech("user_barge_in")
            self.turn_audio.clear()
            self.in_speech = False
            self.explicit_turn = True
            self.silence_ms = 0
            self.speech_ms = 0
            self.last_partial_at_ms = 0
            self.asr.reset()
            await self.send_event("state", value="listening")
        elif event_type == "audio_end":
            self.explicit_turn = False
            if self.turn_audio:
                turn = bytes(self.turn_audio)
                self.turn_audio.clear()
                self.in_speech = False
                self._start_turn_task(turn)
        elif event_type == "interrupt":
            await self._cancel_speech(str(payload.get("reason", "user_barge_in")))
        elif event_type == "resume_audio":
            text = self.pending_tts_text
            if text and not (self.tts_task and not self.tts_task.done()):
                self.pending_tts_text = None
                self.tts_task = asyncio.create_task(self._speak(text))
            else:
                await self.send_event("resume", supported=False, reason="no resumable TTS")
        else:
            await self.send_event("error", stage="protocol", detail=f"unknown message type: {event_type or '<empty>'}")

    async def run(self) -> None:
        await self.send_event("connected", protocol=4)
        try:
            while not self.closed:
                message = await self.websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    await self.handle_text(message["text"])
                elif message.get("bytes") is not None:
                    self.pending_audio.extend(message["bytes"])
                    while len(self.pending_audio) >= self.FRAME_BYTES:
                        frame = bytes(self.pending_audio[: self.FRAME_BYTES])
                        del self.pending_audio[: self.FRAME_BYTES]
                        await self._process_frame(frame)
        except WebSocketDisconnect:
            return
        finally:
            self.closed = True
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
        try:
            connection = LiveVoiceConnection(websocket, runtime)
        except RuntimeError as exc:
            # e.g. TOM_TTS_ENGINE misconfigured: tell the client instead of a bare 1011 close.
            await websocket.send_text(json.dumps({"type": "error", "stage": "startup", "detail": str(exc)}))
            await websocket.close(code=1011)
            return
        try:
            await connection.run()
        except (ValueError, KeyError, RuntimeError) as exc:
            logger.warning("voice websocket protocol error: %s", exc)
            try:
                await websocket.send_text(json.dumps({"type": "error", "stage": "protocol", "detail": str(exc)}))
            except (WebSocketDisconnect, RuntimeError):
                pass

    return router
