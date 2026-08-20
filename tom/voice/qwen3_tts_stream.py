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
    emit_every_frames: int = int(os.getenv("TOM_QWEN3_TTS_EMIT_FRAMES", "6"))
    decode_window_frames: int = int(os.getenv("TOM_QWEN3_TTS_DECODE_WINDOW", "72"))
    first_chunk_emit_every: int = int(os.getenv("TOM_QWEN3_TTS_FIRST_EMIT_FRAMES", "4"))
    first_chunk_frames: int = int(os.getenv("TOM_QWEN3_TTS_FIRST_CHUNK_FRAMES", "24"))
    max_frames: int = int(os.getenv("TOM_QWEN3_TTS_MAX_FRAMES", "10000"))
    overlap_samples: int = int(os.getenv("TOM_QWEN3_TTS_OVERLAP_SAMPLES", "0"))
    streaming: bool = os.getenv("TOM_QWEN3_TTS_STREAMING", "true").lower() not in {"0", "false", "no"}
    voice_design_enabled: bool = os.getenv("TOM_QWEN3_TTS_VOICE_DESIGN", "false").lower() in {"1", "true", "yes"}
    stream_url: str | None = os.getenv("TOM_QWEN3_TTS_STREAM_URL") or None
    # SDPA is the safer default for long-running reliability; FlashAttention 2
    # remains available as an explicit opt-in performance setting.
    attn_implementation: str | None = os.getenv("TOM_QWEN3_TTS_ATTN", "sdpa") or None


class Qwen3TTSStreamingAdapter:
    """Qwen3-TTS adapter with true token/codec streaming when available.

    The official Qwen3-TTS checkpoints support streaming speech generation and
    expressive instructions. TOM keeps CustomVoice as the stable default for a
    consistent companion timbre and only enables VoiceDesign explicitly.

    TOM's current language router sends English here. Hindi/Hinglish/Bengali are
    intentionally handled by the Indic backend because the official Qwen3-TTS
    model family does not list those languages as supported target languages.
    """

    SAMPLE_RATE = 24000
    STREAM_MAGIC = b"TOMQWEN1"
    FRAME_AUDIO = 0
    FRAME_ERROR = 1
    FRAME_END = 2
    SUPPORTED_TOM_LANGUAGES: ClassVar[set[Language]] = {Language.EN}

    _LANGUAGE_NAMES: ClassVar[dict[Language, str]] = {
        Language.EN: "English",
    }

    _SPEAKERS: ClassVar[dict[str, str]] = {
        "tom_m1": "Ryan",
        "tom_m2": "Aiden",
        "tom_f1": "Serena",
    }

    def __init__(self, config: Qwen3VoiceConfig | None = None) -> None:
        self.config = config or Qwen3VoiceConfig()
        self._custom_model: Any = None
        self._design_model: Any = None
        self._torch: Any = None

    def _load(self, *, design: bool = False) -> Any:
        if design:
            raise RuntimeError("Qwen3-TTS production path supports CustomVoice only")
        slot = "_design_model" if design else "_custom_model"
        existing = getattr(self, slot)
        if existing is not None:
            return existing

        # TOM safety gate: never let a local Qwen load exhaust the Codespaces host.
        # Qwen3-TTS 0.6B is intended for machines with substantially more memory
        # than a small Codespaces container when running on CPU.
        min_ram_gb = float(os.getenv("TOM_QWEN3_TTS_MIN_RAM_GB", "8"))
        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
        except Exception:
            available_gb = 0.0

        use_cuda = False
        try:
            import torch
            use_cuda = bool(torch.cuda.is_available())
            if use_cuda:
                free_bytes, _ = torch.cuda.mem_get_info()
                min_vram_gb = float(os.getenv("TOM_QWEN3_TTS_MIN_VRAM_GB", "4"))
                if free_bytes / (1024 ** 3) < min_vram_gb:
                    raise RuntimeError(
                        f"Qwen3-TTS skipped: only {free_bytes/(1024**3):.2f} GB GPU memory free"
                    )
            elif available_gb < min_ram_gb:
                raise RuntimeError(
                    f"Qwen3-TTS skipped: only {available_gb:.2f} GB RAM available; "
                    f"{min_ram_gb:.1f} GB required for safe local CPU inference"
                )
        except RuntimeError:
            raise
        except Exception:
            if available_gb < min_ram_gb:
                raise RuntimeError(
                    f"Qwen3-TTS skipped: only {available_gb:.2f} GB RAM available"
                )
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError(
                "Qwen3-TTS dependencies are missing. Install the TOM voice-qwen extra."
            ) from exc
        self._torch = torch
        model_path = self.config.model_dir.strip()
        if not os.path.isdir(model_path):
            raise RuntimeError(f"MODEL_NOT_DOWNLOADED: {model_path}")
        use_cuda = bool(torch.cuda.is_available())
        device = ("cuda:0" if use_cuda else "cpu") if self.config.device == "auto" else self.config.device
        dtype_name = self.config.dtype if use_cuda else os.getenv("TOM_QWEN3_TTS_CPU_DTYPE", "float32")
        dtype = getattr(torch, dtype_name, torch.float32)
        kwargs: dict[str, Any] = {"dtype": dtype}
        if device:
            kwargs["device_map"] = device
        if self.config.attn_implementation:
            kwargs["attn_implementation"] = self.config.attn_implementation

        # Codespaces/CPU-safe path: do not compile/stream-optimize on CPU.
        use_cuda = bool(torch.cuda.is_available())
        model = Qwen3TTSModel.from_pretrained(model_path, **kwargs)

        enable = getattr(model, "enable_streaming_optimizations", None)
        if callable(enable) and self.config.streaming and use_cuda:
            try:
                enable(
                    decode_window_frames=self.config.decode_window_frames,
                    use_compile=os.getenv("TOM_QWEN3_TTS_COMPILE", "true").lower() not in {"0", "false", "no"},
                    compile_mode=os.getenv("TOM_QWEN3_TTS_COMPILE_MODE", "reduce-overhead"),
                )
            except Exception:  # noqa: BLE001, S110
                pass
        setattr(self, slot, model)
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
        pause = "slightly longer phrase pauses" if style.pause_scale > 1.1 else "tight natural phrase pauses" if style.pause_scale < 0.9 else "natural phrase pauses"
        character_hint = f" Character identity: {character}." if character else ""
        trait_hint = f" Character traits: {traits}." if traits else ""
        return (
            f"Speak in a {emotion}, {intensity}, {warmth}, {pitch} conversational style at a {rate} rate, "
            f"with realistic pauses, {pause}, and {breath}. Keep breaths subtle and do not breathe on every phrase. "
            "Sound like a real person speaking naturally to one familiar person, not like a narrator or announcer. "
            "Avoid theatrical overacting, exaggerated emotion, robotic cadence, forced laughter, and filler words. "
            "Do not read markdown, stage directions, emoji names, or formatting instructions aloud."
            f"{character_hint}{trait_hint}"
        )

    def _validate_language(self, language: Language) -> None:
        if language not in self.SUPPORTED_TOM_LANGUAGES:
            raise RuntimeError(
                f"Qwen3-TTS backend is not configured for TOM language '{language.value}'. "
                "Use the hybrid/Indic voice router for Hindi, Hinglish, or Bengali."
            )

    def _generate(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> tuple[Any, int]:
        self._validate_language(language)
        model = self._load()
        language_name = self._LANGUAGE_NAMES[language]
        instruction = str(style.prosody_plan.get("instruction") or self._instruction(
            style,
            character=str(style.prosody_plan.get("character", voice.label)),
            traits=str(style.prosody_plan.get("character_traits", "")),
        ))
        kwargs = {
            "do_sample": True,
            "temperature": float(style.prosody_plan.get("temperature", 0.62)),
            "top_p": float(style.prosody_plan.get("top_p", 0.90)),
        }
        speaker = self._SPEAKERS.get(voice.id, "Ryan")
        wavs, sr = model.generate_custom_voice(
            text=text, language=language_name, speaker=speaker, instruct=instruction, **kwargs
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
            if array.ndim > 2 or (array.ndim == 2 and 1 not in array.shape):
                raise RuntimeError(f"Qwen3-TTS returned unsupported channel shape: {array.shape}")
            if array.size == 0 or not np.isfinite(array).all():
                raise RuntimeError("Qwen3-TTS returned empty or non-finite audio")
            if array.size > self.config.max_frames * (self.SAMPLE_RATE // 12):
                raise RuntimeError("Qwen3-TTS returned audio longer than the configured limit")
        except ImportError as exc:
            raise RuntimeError("numpy is required for Qwen3-TTS audio validation") from exc
        return waveform, sample_rate

    @staticmethod
    def _to_pcm16_bytes(chunk: Any) -> bytes:
        if isinstance(chunk, (bytes, bytearray, memoryview)):
            return bytes(chunk)
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("numpy is required for array-based Qwen3-TTS streaming") from exc
        if hasattr(chunk, "detach"):
            chunk = chunk.detach().float().cpu().numpy()
        pcm = np.asarray(chunk)
        if pcm.dtype.kind == "f":
            pcm = np.clip(pcm.reshape(-1), -1.0, 1.0)
            return (pcm * 32767.0).astype(np.int16).tobytes()
        return pcm.reshape(-1).astype(np.int16, copy=False).tobytes()

    def _stream_local(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk] | None:
        if not self.config.streaming:
            return None
        self._validate_language(language)
        waveform, sample_rate = self._generate(text, language, voice, style)
        pcm16 = self._to_pcm16_bytes(waveform)
        packet_bytes = max(320, int(self.SAMPLE_RATE * self.config.chunk_ms / 1000) * 2)
        for offset in range(0, len(pcm16), packet_bytes):
            yield TTSChunk(pcm16=pcm16[offset:offset + packet_bytes], sample_rate=sample_rate)

    def _stream_http(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        self._validate_language(language)
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for TOM_QWEN3_TTS_STREAM_URL") from exc
        speaker = self._SPEAKERS.get(voice.id, "Ryan")
        language_name = self._LANGUAGE_NAMES[language]
        instruction = self._instruction(
            style,
            character=str(style.prosody_plan.get("character", voice.label)),
            traits=str(style.prosody_plan.get("character_traits", "")),
        )
        payload = {
            "input": text,
            "voice": speaker,
            "model": self.config.model_id,
            "language": language_name,
            "instruct": instruction,
            "stream": True,
            "response_format": "pcm",
        }
        with httpx.stream("POST", self.config.stream_url, json=payload, timeout=None) as response:
            response.raise_for_status()
            expected_format = response.headers.get("x-tom-audio-format")
            expected_rate = response.headers.get("x-tom-sample-rate")
            expected_channels = response.headers.get("x-tom-channels")
            if expected_format != "pcm_s16le" or expected_rate != str(self.SAMPLE_RATE) or expected_channels != "1":
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
                    if frame_size > 4 * 1024 * 1024:
                        raise RuntimeError("Qwen3-TTS stream frame is too large")
                    if len(buffer) < 5 + frame_size:
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
        if self.config.streaming:
            local_stream = self._stream_local(prompt, language, voice, style)
            yield from local_stream
            return
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("numpy is required for Qwen3-TTS") from exc
        waveform, sample_rate = self._generate(prompt, language, voice, style)
        pcm16 = self._to_pcm16_bytes(np.asarray(waveform, dtype=np.float32))
        packet_bytes = max(320, int(sample_rate * self.config.chunk_ms / 1000) * 2)
        for offset in range(0, len(pcm16), packet_bytes):
            yield TTSChunk(pcm16=pcm16[offset:offset + packet_bytes], sample_rate=sample_rate)
