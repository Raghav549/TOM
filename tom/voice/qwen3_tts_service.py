from __future__ import annotations

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
        _adapter = Qwen3TTSStreamingAdapter(replace(Qwen3VoiceConfig(), stream_url=None))
    return _adapter


def _voice(voice: str) -> VoiceProfile:
    for voice_id, speaker in Qwen3TTSStreamingAdapter._SPEAKERS.items():
        if voice.casefold() == speaker.casefold():
            return VOICE_PROFILES[voice_id]
    return VOICE_PROFILES["tom_m1"]


def _frame(frame_type: int, payload: bytes = b"") -> bytes:
    return bytes([frame_type]) + struct.pack(">I", len(payload)) + payload


def _stream(request: Qwen3TTSRequest) -> Iterator[bytes]:
    adapter = _adapter_for_service()
    style = VoiceStyle(prosody_plan={"temperature": request.temperature, "top_p": request.top_p})
    if request.instruct.strip():
        style = replace(style, prosody_plan={**style.prosody_plan, "instruction": request.instruct.strip()})
    voice = _voice(request.voice)
    try:
        for chunk in adapter._stream_local(request.input, Language.EN, voice, style) or ():
            yield _frame(adapter.FRAME_AUDIO, chunk.pcm16)
        yield _frame(adapter.FRAME_END)
    except GeneratorExit:
        return
    except Exception as exc:  # noqa: BLE001 - encoded in the streaming contract
        yield _frame(adapter.FRAME_ERROR, str(exc).encode("utf-8", "replace")[:4096])


@router.post("/stream")
async def stream_qwen3(request: Qwen3TTSRequest) -> StreamingResponse:
    if request.language.casefold() not in {"en", "english"}:
        raise HTTPException(status_code=422, detail="Qwen3-TTS production endpoint currently supports English only")
    adapter = _adapter_for_service()
    try:
        adapter._validate_language(Language.EN)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StreamingResponse(
        iter(_stream(request)),
        media_type="application/octet-stream",
        headers={
            "x-tom-audio-format": "pcm_s16le",
            "x-tom-sample-rate": str(adapter.SAMPLE_RATE),
            "x-tom-stream-protocol": "TOM-QWEN3-PCM/1; frame=type:u8,length:u32be; end=2; error=1",
            "cache-control": "no-store",
        },
    )


@router.get("/health")
async def qwen3_health() -> dict[str, str]:
    adapter = _adapter_for_service()
    try:
        adapter._load()
    except Exception as exc:  # noqa: BLE001 - readiness must expose model failure
        raise HTTPException(status_code=503, detail=f"Qwen3-TTS model unavailable: {exc}") from exc
    return {"status": "ok", "model": adapter.config.model_id, "audio_format": "pcm_s16le", "sample_rate": str(adapter.SAMPLE_RATE)}