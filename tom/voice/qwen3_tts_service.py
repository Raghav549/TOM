from __future__ import annotations

import asyncio
import struct
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .models import Language, VoiceProfile, VoiceStyle, VOICE_PROFILES
from .qwen3_tts_stream import Qwen3TTSStreamingAdapter, Qwen3VoiceConfig


class Qwen3TTSRequest(BaseModel):
    input: str = Field(min_length=1, max_length=4000)
    voice: str = "Ryan"
    model: str | None = None
    language: str = "English"
    instruct: str = ""
    temperature: float = Field(default=0.62, ge=0.0, le=2.0)
    top_p: float = Field(default=0.90, gt=0.0, le=1.0)


router = APIRouter(prefix="/v1/tts/qwen3", tags=["qwen3-tts"])
_adapter: Qwen3TTSStreamingAdapter | None = None


def _adapter_for_service() -> Qwen3TTSStreamingAdapter:
    global _adapter
    if _adapter is None:
        _adapter = Qwen3TTSStreamingAdapter(replace(Qwen3VoiceConfig(), stream_url=None, streaming=True))
    return _adapter


def _voice(voice: str) -> VoiceProfile:
    for voice_id, speaker in Qwen3TTSStreamingAdapter._SPEAKERS.items():
        if voice.casefold() == speaker.casefold():
            return VOICE_PROFILES[voice_id]
    return VOICE_PROFILES["tom_m1"]


def _frame(frame_type: int, payload: bytes = b"") -> bytes:
    return bytes([frame_type]) + struct.pack(">I", len(payload)) + payload


def _stream(chunks: list[Any], adapter: Qwen3TTSStreamingAdapter) -> Iterator[bytes]:
    yield adapter.STREAM_MAGIC
    for chunk in chunks:
        yield _frame(adapter.FRAME_AUDIO, chunk.pcm16)
    yield _frame(adapter.FRAME_END)


def _generate(request: Qwen3TTSRequest, adapter: Qwen3TTSStreamingAdapter) -> list[Any]:
    style = VoiceStyle(prosody_plan={"temperature": request.temperature, "top_p": request.top_p})
    if request.instruct.strip():
        style = style.model_copy(update={"prosody_plan": {**style.prosody_plan, "instruction": request.instruct.strip()}})
    voice = _voice(request.voice)
    chunks = list(adapter._stream_local(request.input, Language.EN, voice, style))
    if not chunks or not any(chunk.pcm16 for chunk in chunks):
        raise RuntimeError("Qwen3-TTS returned no audio")
    return chunks


@router.post("/stream")
async def stream_qwen3(request: Qwen3TTSRequest) -> StreamingResponse:
    if request.language.casefold() not in {"en", "english"}:
        raise HTTPException(status_code=422, detail="Qwen3-TTS production endpoint currently supports English only")
    if request.model and request.model != Qwen3VoiceConfig().model_id:
        raise HTTPException(status_code=422, detail="only Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice is supported")
    adapter = _adapter_for_service()
    try:
        adapter._validate_language(Language.EN)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        chunks = await asyncio.to_thread(_generate, request, adapter)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StreamingResponse(
        _stream(chunks, adapter),
        media_type="application/octet-stream",
        headers={
            "x-tom-audio-format": "pcm_s16le",
            "x-tom-sample-rate": str(adapter.SAMPLE_RATE),
            "x-tom-channels": "1",
            "x-tom-stream-protocol": "TOM-QWEN3-PCM/1; frame=type:u8,length:u32be; end=2; error=1",
            "cache-control": "no-store",
        },
    )


@router.get("/health")
async def qwen3_health() -> dict[str, str]:
    adapter = _adapter_for_service()
    try:
        adapter._load()
    except RuntimeError as exc:
        detail = str(exc)
        if detail.startswith("MODEL_NOT_DOWNLOADED"):
            code = "MODEL_NOT_DOWNLOADED"
        elif "dependencies are missing" in detail or "cannot import" in detail:
            code = "DEPENDENCY_ERROR"
        elif "GPU" in detail or "RAM" in detail or "memory" in detail:
            code = "CPU/GPU_UNAVAILABLE"
        else:
            code = "MODEL_LOAD_ERROR"
        raise HTTPException(status_code=503, detail={"status": code, "detail": detail}) from exc
    except Exception as exc:  # noqa: BLE001 - readiness must expose model failure
        raise HTTPException(status_code=503, detail={"status": "MODEL_LOAD_ERROR", "detail": str(exc)}) from exc
    return {"status": "READY", "model": adapter.config.model_id, "model_dir": adapter.config.model_dir, "audio_format": "pcm_s16le", "sample_rate": str(adapter.SAMPLE_RATE), "channels": "1"}