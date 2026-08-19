from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


@dataclass(frozen=True)
class Qwen3VoiceConfig:
    model_id: str = os.getenv("TOM_QWEN3_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
    voice_design_model_id: str = os.getenv("TOM_QWEN3_TTS_VOICE_DESIGN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
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
        device = None if self.config.device == "auto" else self.config.device
        dtype = getattr(torch, self.config.dtype, torch.bfloat16)
        model_id = self.config.voice_design_model_id if design else self.config.model_id
        kwargs: dict[str, Any] = {"dtype": dtype}
        if device:
            kwargs["device_map"] = device
        if self.config.attn_implementation:
            kwargs["attn_implementation"] = self.config.attn_implementation

        # Codespaces/CPU-safe path: do not compile/stream-optimize on CPU.
        use_cuda = bool(torch.cuda.is_available())
        model = Qwen3TTSModel.from_pretrained(model_id, **kwargs)

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
        use_design = bool(style.prosody_plan.get("voice_design", self.config.voice_design_enabled))
        model = self._load(design=use_design)
        language_name = self._LANGUAGE_NAMES[language]
        instruction = self._instruction(
            style,
            character=str(style.prosody_plan.get("character", voice.label)),
            traits=str(style.prosody_plan.get("character_traits", "")),
        )
        kwargs = {
            "do_sample": True,
            "temperature": float(style.prosody_plan.get("temperature", 0.62)),
            "top_p": float(style.prosody_plan.get("top_p", 0.90)),
        }
        if use_design:
            wavs, sr = model.generate_voice_design(
                text=text, language=language_name, instruct=instruction, **kwargs
            )
        else:
            speaker = self._SPEAKERS.get(voice.id, "Ryan")
            wavs, sr = model.generate_custom_voice(
                text=text, language=language_name, speaker=speaker, instruct=instruction, **kwargs
            )
        return wavs[0], int(sr)

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
        use_design = bool(style.prosody_plan.get("voice_design", self.config.voice_design_enabled))
        model = self._load(design=use_design)
        language_name = self._LANGUAGE_NAMES[language]
        instruction = self._instruction(
            style,
            character=str(style.prosody_plan.get("character", voice.label)),
            traits=str(style.prosody_plan.get("character_traits", "")),
        )
        common = {
            "do_sample": True,
            "temperature": float(style.prosody_plan.get("temperature", 0.62)),
            "top_p": float(style.prosody_plan.get("top_p", 0.90)),
            "emit_every_frames": self.config.emit_every_frames,
            "decode_window_frames": self.config.decode_window_frames,
            "overlap_samples": self.config.overlap_samples,
            "max_frames": self.config.max_frames,
        }
        if self.config.first_chunk_emit_every > 0:
            common.update(
                first_chunk_emit_every=self.config.first_chunk_emit_every,
                first_chunk_frames=self.config.first_chunk_frames,
                first_chunk_decode_window=min(48, self.config.decode_window_frames),
            )
        if use_design:
            fn = getattr(model, "stream_generate_voice_design", None)
            if callable(fn):
                for audio, sr in fn(text=text, language=language_name, instruct=instruction, **common):
                    yield TTSChunk(pcm16=self._to_pcm16_bytes(audio), sample_rate=int(sr))
                return
            return None
        speaker = self._SPEAKERS.get(voice.id, "Ryan")
        fn = getattr(model, "stream_generate_custom_voice", None)
        if callable(fn):
            for audio, sr in fn(text=text, language=language_name, speaker=speaker, instruct=instruction, **common):
                yield TTSChunk(pcm16=self._to_pcm16_bytes(audio), sample_rate=int(sr))
            return
        return None

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
            for data in response.iter_bytes():
                if data:
                    yield TTSChunk(pcm16=data, sample_rate=self.SAMPLE_RATE)

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        prompt = text.strip()
        if not prompt:
            return
        self._validate_language(language)
        if self.config.stream_url:
            yield from self._stream_http(prompt, language, voice, style)
            return
        # CPU/Codespaces: use reliable non-streaming generation.
        # True streaming remains enabled automatically on CUDA.
        import torch
        if torch.cuda.is_available() and self.config.streaming:
            local_stream = self._stream_local(prompt, language, voice, style)
            if local_stream is not None:
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
