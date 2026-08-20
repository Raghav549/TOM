from __future__ import annotations

import os
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


@dataclass(frozen=True)
class Qwen3VoiceConfig:
    model_id: str = os.getenv("TOM_QWEN3_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
    model_dir: str = os.getenv("TOM_QWEN3_TTS_MODEL_DIR", ".models/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
    device: str = os.getenv("TOM_QWEN3_TTS_DEVICE", "auto")
    dtype: str = os.getenv("TOM_QWEN3_TTS_DTYPE", "bfloat16")
    chunk_ms: int = int(os.getenv("TOM_QWEN3_TTS_CHUNK_MS", "80"))
    decode_window_frames: int = int(os.getenv("TOM_QWEN3_TTS_DECODE_WINDOW", "72"))
    max_frames: int = int(os.getenv("TOM_QWEN3_TTS_MAX_FRAMES", "10000"))
    streaming: bool = os.getenv("TOM_QWEN3_TTS_STREAMING", "true").lower() not in {"0", "false", "no"}
    stream_url: str | None = os.getenv("TOM_QWEN3_TTS_STREAM_URL") or None
    attn_implementation: str | None = os.getenv("TOM_QWEN3_TTS_ATTN", "sdpa") or None


class Qwen3TTSStreamingAdapter:
    """Real Qwen3-TTS CustomVoice adapter with deterministic PCM16 chunking."""

    SAMPLE_RATE = 24000
    STREAM_MAGIC = b"TOMQWEN1"
    FRAME_AUDIO = 0
    FRAME_ERROR = 1
    FRAME_END = 2
    SUPPORTED_TOM_LANGUAGES: ClassVar[set[Language]] = {Language.EN}

    _LANGUAGE_NAMES: ClassVar[dict[Language, str]] = {Language.EN: "English"}
    _SPEAKERS: ClassVar[dict[str, str]] = {"tom_m1": "Ryan", "tom_m2": "Aiden", "tom_f1": "Serena"}

    def __init__(self, config: Qwen3VoiceConfig | None = None) -> None:
        self.config = config or Qwen3VoiceConfig()
        self._custom_model: Any = None
        self._torch: Any = None

    def _load(self) -> Any:
        if self._custom_model is not None:
            return self._custom_model
        min_ram_gb = float(os.getenv("TOM_QWEN3_TTS_MIN_RAM_GB", "8"))
        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
        except Exception:
            available_gb = 0.0
        try:
            import torch
            use_cuda = bool(torch.cuda.is_available())
            if use_cuda:
                free_bytes, _ = torch.cuda.mem_get_info()
                min_vram_gb = float(os.getenv("TOM_QWEN3_TTS_MIN_VRAM_GB", "4"))
                if free_bytes / (1024 ** 3) < min_vram_gb:
                    raise RuntimeError(f"Qwen3-TTS skipped: only {free_bytes/(1024**3):.2f} GB GPU memory free")
            elif available_gb < min_ram_gb:
                raise RuntimeError(f"Qwen3-TTS skipped: only {available_gb:.2f} GB RAM available; {min_ram_gb:.1f} GB required")
        except RuntimeError:
            raise
        except Exception:
            if available_gb < min_ram_gb:
                raise RuntimeError(f"Qwen3-TTS skipped: only {available_gb:.2f} GB RAM available")
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError("Qwen3-TTS dependencies are missing. Install the TOM voice-qwen extra.") from exc
        self._torch = torch
        model_path = self.config.model_dir.strip()
        if not os.path.isdir(model_path):
            raise RuntimeError(f"MODEL_NOT_DOWNLOADED: {model_path}")
        device = ("cuda:0" if torch.cuda.is_available() else "cpu") if self.config.device == "auto" else self.config.device
        dtype_name = self.config.dtype if torch.cuda.is_available() else os.getenv("TOM_QWEN3_TTS_CPU_DTYPE", "float32")
        dtype = getattr(torch, dtype_name, torch.float32)
        kwargs: dict[str, Any] = {"dtype": dtype}
        if device:
            kwargs["device_map"] = device
        if self.config.attn_implementation:
            kwargs["attn_implementation"] = self.config.attn_implementation
        model = Qwen3TTSModel.from_pretrained(model_path, **kwargs)
        self._custom_model = model
        return model

    @staticmethod
    def _instruction(style: VoiceStyle, *, character: str = "", traits: str = "") -> str:
        requested = str(style.prosody_plan.get("instruction", "")).strip()
        if requested:
            return requested
        emotion = style.emotion.value
        rate = "slower" if style.speaking_rate < 0.9 else "faster" if style.speaking_rate > 1.1 else "moderate"
        pitch = "lower-pitched" if style.pitch_shift < -0.15 else "higher-pitched" if style.pitch_shift > 0.15 else "natural-pitch"
        intensity = "subtle" if style.intensity < 0.4 else "expressive" if style.intensity < 0.75 else "highly expressive"
        breath = "with audible natural micro-breath timing" if style.breathiness >= 0.35 else "with natural breath timing"
        warmth = "warm and intimate" if style.warmth >= 0.7 else "clear and conversational"
        character_hint = f" Character identity: {character}." if character else ""
        trait_hint = f" Character traits: {traits}." if traits else ""
        return (
            f"Speak in a {emotion}, {intensity}, {warmth}, {pitch} conversational style at a {rate} rate, "
            f"with realistic pauses and {breath}. Sound like a real person speaking naturally to one familiar person. "
            "Avoid theatrical overacting, robotic cadence, forced laughter, and filler words. "
            "Do not read markdown, stage directions, emoji names, or formatting instructions aloud."
            f"{character_hint}{trait_hint}"
        )

    def _validate_language(self, language: Language) -> None:
        if language not in self.SUPPORTED_TOM_LANGUAGES:
            raise RuntimeError(f"Qwen3-TTS production backend currently supports {sorted(x.value for x in self.SUPPORTED_TOM_LANGUAGES)} only; got {language.value}")

    def _generate(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> tuple[Any, int]:
        self._validate_language(language)
        model = self._load()
        instruction = str(style.prosody_plan.get("instruction") or self._instruction(style, character=str(style.prosody_plan.get("character", voice.label)), traits=str(style.prosody_plan.get("character_traits", ""))))
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=self._LANGUAGE_NAMES[language],
            speaker=self._SPEAKERS.get(voice.id, "Ryan"),
            instruct=instruction,
            do_sample=True,
            temperature=float(style.prosody_plan.get("temperature", 0.62)),
            top_p=float(style.prosody_plan.get("top_p", 0.90)),
        )
        if not wavs:
            raise RuntimeError("Qwen3-TTS returned no waveform")
        sample_rate = int(sr)
        if sample_rate != self.SAMPLE_RATE:
            raise RuntimeError(f"Qwen3-TTS returned unsupported sample rate: {sample_rate}")
        waveform = wavs[0]
        try:
            import numpy as np
            array = waveform.detach().float().cpu().numpy() if hasattr(waveform, "detach") else np.asarray(waveform)
            if array.size == 0 or not np.isfinite(array).all():
                raise RuntimeError("Qwen3-TTS returned empty or non-finite audio")
        except ImportError as exc:
            raise RuntimeError("numpy is required for Qwen3-TTS audio validation") from exc
        return waveform, sample_rate

    @staticmethod
    def _to_pcm16_bytes(chunk: Any) -> bytes:
        if isinstance(chunk, (bytes, bytearray, memoryview)):
            return bytes(chunk)
        import numpy as np
        if hasattr(chunk, "detach"):
            chunk = chunk.detach().float().cpu().numpy()
        pcm = np.asarray(chunk).reshape(-1)
        if pcm.dtype.kind == "f":
            pcm = np.clip(pcm, -1.0, 1.0)
            return (pcm * 32767.0).astype(np.int16).tobytes()
        return pcm.astype(np.int16, copy=False).tobytes()

    def _stream_local(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        waveform, sample_rate = self._generate(text, language, voice, style)
        pcm16 = self._to_pcm16_bytes(waveform)
        packet_bytes = max(320, int(self.SAMPLE_RATE * self.config.chunk_ms / 1000) * 2)
        for offset in range(0, len(pcm16), packet_bytes):
            yield TTSChunk(pcm16=pcm16[offset:offset + packet_bytes], sample_rate=sample_rate)

    def _stream_http(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        self._validate_language(language)
        import httpx
        instruction = self._instruction(style, character=str(style.prosody_plan.get("character", voice.label)), traits=str(style.prosody_plan.get("character_traits", "")))
        payload = {"input": text, "voice": self._SPEAKERS.get(voice.id, "Ryan"), "model": self.config.model_id, "language": "English", "instruct": instruction, "stream": True, "response_format": "pcm"}
        headers = {}
        token = os.getenv("TOM_QWEN3_TTS_AUTH_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.stream("POST", self.config.stream_url, json=payload, headers=headers, timeout=None) as response:
            response.raise_for_status()
            if response.headers.get("x-tom-audio-format") != "pcm_s16le" or response.headers.get("x-tom-sample-rate") != str(self.SAMPLE_RATE) or response.headers.get("x-tom-channels") != "1":
                raise RuntimeError("Qwen3-TTS stream contract headers are invalid")
            buffer = bytearray()
            magic_checked = False
            ended = False
            for data in response.iter_bytes():
                buffer.extend(data)
                if not magic_checked:
                    if len(buffer) < len(self.STREAM_MAGIC):
                        continue
                    if bytes(buffer[:len(self.STREAM_MAGIC)]) != self.STREAM_MAGIC:
                        raise RuntimeError("Qwen3-TTS stream magic is invalid")
                    del buffer[:len(self.STREAM_MAGIC)]
                    magic_checked = True
                while len(buffer) >= 5:
                    frame_type = buffer[0]
                    frame_size = struct.unpack(">I", buffer[1:5])[0]
                    if frame_size > 4 * 1024 * 1024 or len(buffer) < 5 + frame_size:
                        if frame_size > 4 * 1024 * 1024:
                            raise RuntimeError("Qwen3-TTS stream frame is too large")
                        break
                    frame = bytes(buffer[5:5 + frame_size])
                    del buffer[:5 + frame_size]
                    if frame_type == self.FRAME_AUDIO:
                        if not frame or len(frame) % 2:
                            raise RuntimeError("Qwen3-TTS audio frame is not PCM16")
                        yield TTSChunk(pcm16=frame, sample_rate=self.SAMPLE_RATE)
                    elif frame_type == self.FRAME_ERROR:
                        raise RuntimeError(frame.decode("utf-8", "replace") or "Qwen3-TTS server error")
                    elif frame_type == self.FRAME_END:
                        ended = True
                        break
                    else:
                        raise RuntimeError("Qwen3-TTS stream frame type is invalid")
                if ended:
                    break
            if not ended:
                raise RuntimeError("Qwen3-TTS stream ended without an end frame")

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        prompt = text.strip()
        if not prompt:
            return
        self._validate_language(language)
        if self.config.stream_url:
            yield from self._stream_http(prompt, language, voice, style)
            return
        yield from self._stream_local(prompt, language, voice, style)
