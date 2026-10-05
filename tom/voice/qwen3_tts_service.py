from __future__ import annotations

import asyncio
import os
import secrets
import struct
import threading
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .models import VOICE_PROFILES, Language, VoiceProfile, VoiceStyle
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
_generation_slot = threading.BoundedSemaphore(1)


def _adapter_for_service() -> Qwen3TTSStreamingAdapter:
    global _adapter
    if _adapter is None:
        _adapter = Qwen3TTSStreamingAdapter(replace(Qwen3VoiceConfig(), stream_url=None, streaming=True))
    return _adapter


def _voice(voice: str) -> VoiceProfile:
    for voice_id, speaker in Qwen3TTSStreamingAdapter._SPEAKERS.items():
        if voice.casefold() == speaker.casefold():
            return VOICE_PROFILES[voice_id]
    raise HTTPException(status_code=422, detail="Unsupported voice; choose Ryan, Aiden, or Serena")


def _frame(frame_type: int, payload: bytes = b"") -> bytes:
    return bytes([frame_type]) + struct.pack(">I", len(payload)) + payload


def _stream(chunks: list[Any], adapter: Qwen3TTSStreamingAdapter) -> Iterator[bytes]:
    yield adapter.STREAM_MAGIC
    for chunk in chunks:
        yield _frame(adapter.FRAME_AUDIO, chunk.pcm16)
    yield _frame(adapter.FRAME_END)


def _auth_required() -> bool:
    return os.getenv("TOM_ENV", "development").strip().lower() == "production"


def _auth_token() -> str:
    return os.getenv("TOM_QWEN3_TTS_AUTH_TOKEN", "").strip()


def _authorize(access_token: str | None) -> None:
    expected = _auth_token()
    if not _auth_required() and not expected:
        return
    if not expected:
        raise HTTPException(status_code=503, detail="Qwen3-TTS public API auth is not configured")
    if not access_token or not secrets.compare_digest(access_token, expected):
        raise HTTPException(status_code=401, detail="invalid Qwen3-TTS access token")


def _generate(request: Qwen3TTSRequest, adapter: Qwen3TTSStreamingAdapter) -> list[Any]:
    # Hold the slot in the worker, not the HTTP coroutine: disconnecting a
    # client cannot release GPU capacity while native inference is still running.
    if not _generation_slot.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="TTS is busy; retry after generation completes")
    try:
        return _generate_audio(request, adapter)
    finally:
        _generation_slot.release()


def _generate_audio(request: Qwen3TTSRequest, adapter: Qwen3TTSStreamingAdapter) -> list[Any]:
    style = VoiceStyle(prosody_plan={"temperature": request.temperature, "top_p": request.top_p})
    if request.instruct.strip():
        style = style.model_copy(update={"prosody_plan": {**style.prosody_plan, "instruction": request.instruct.strip()}})
    voice = _voice(request.voice)
    chunks = list(adapter._stream_local(request.input, Language.EN, voice, style))
    if not chunks or not any(chunk.pcm16 for chunk in chunks):
        raise RuntimeError("Qwen3-TTS returned no audio")
    return chunks


async def _stream_qwen3(request: Qwen3TTSRequest, access_token: str | None = None) -> StreamingResponse:
    _authorize(access_token)
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
            "x-tom-generation-mode": "buffered-inference",
        },
    )


@router.post("/stream")
async def stream_qwen3(request: Qwen3TTSRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    return await _stream_qwen3(request, token)


@router.post("/stream/{access_token}")
async def stream_qwen3_authenticated(request: Qwen3TTSRequest, access_token: str) -> StreamingResponse:
    """Bearer-by-path variant used by free temporary tunnel deployments.

    A named production tunnel should prefer a normal Authorization header at
    the edge. The tokenized route exists so the zero-cost Kaggle + TryCloudflare
    deployment can be reached without exposing the TTS endpoint anonymously.
    """
    return await _stream_qwen3(request, access_token)


@router.get("/health")
async def qwen3_health() -> dict[str, str]:
    if _auth_required() and not _auth_token():
        raise HTTPException(
            status_code=503,
            detail={"status": "AUTH_NOT_CONFIGURED", "detail": "set TOM_QWEN3_TTS_AUTH_TOKEN for public production TTS"},
        )
    adapter = _adapter_for_service()
    try:
        await asyncio.to_thread(adapter._load)
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
    return {
        "status": "READY",
        "model": adapter.config.model_id,
        "model_dir": adapter.config.model_dir,
        "audio_format": "pcm_s16le",
        "sample_rate": str(adapter.SAMPLE_RATE),
        "channels": "1",
        "generation_mode": "buffered-inference",
        "public_auth": "required" if _auth_required() else "disabled",
    }
