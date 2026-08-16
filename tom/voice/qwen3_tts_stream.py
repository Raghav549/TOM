from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


@dataclass(frozen=True)
class Qwen3VoiceConfig:
    model_id: str = os.getenv("TOM_QWEN3_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    voice_design_model_id: str = os.getenv("TOM_QWEN3_TTS_VOICE_DESIGN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    device: str = os.getenv("TOM_QWEN3_TTS_DEVICE", "auto")
    dtype: str = os.getenv("TOM_QWEN3_TTS_DTYPE", "bfloat16")
    chunk_ms: int = int(os.getenv("TOM_QWEN3_TTS_CHUNK_MS", "80"))


class Qwen3TTSStreamingAdapter:
    """Qwen3-TTS expressive adapter with low-latency PCM packetization."""

    SAMPLE_RATE = 24000

    _LANGUAGE_NAMES: ClassVar[dict[Language, str]] = {
        Language.EN: "English",
        Language.HI: "Hindi",
        Language.HINGLISH: "English",
        Language.BN: "Bengali",
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
        model = Qwen3TTSModel.from_pretrained(model_id, **kwargs)
        setattr(self, slot, model)
        return model

    @staticmethod
    def _instruction(style: VoiceStyle, *, character: str = "") -> str:
        emotion = style.emotion.value
        rate = "slower" if style.speaking_rate < 0.9 else "faster" if style.speaking_rate > 1.1 else "moderate"
        pitch = "lower-pitched" if style.pitch_shift < -0.15 else "higher-pitched" if style.pitch_shift > 0.15 else "natural-pitch"
        intensity = "subtle" if style.intensity < 0.4 else "expressive" if style.intensity < 0.75 else "highly expressive"
        breath = "with audible natural micro-breath timing" if style.breathiness >= 0.35 else "with natural breath timing"
        warmth = "warm and intimate" if style.warmth >= 0.7 else "clear and conversational"
        character_hint = f" Character identity: {character}." if character else ""
        return (
            f"Speak in a {emotion}, {intensity}, {warmth}, {pitch} conversational style at a {rate} rate, "
            f"with realistic pauses and {breath}. Avoid theatrical overacting and avoid robotic cadence.{character_hint}"
        )

    def _generate(self, text: str, language: Language, voice: VoiceProfile, style: VoiceStyle) -> tuple[Any, int]:
        use_design = bool(style.prosody_plan.get("voice_design"))
        model = self._load(design=use_design)
        language_name = self._LANGUAGE_NAMES.get(language, "English")
        instruction = self._instruction(style, character=str(style.prosody_plan.get("character", "")))
        if use_design:
            wavs, sr = model.generate_voice_design(
                text=text, language=language_name, instruct=instruction,
                do_sample=True, temperature=float(style.prosody_plan.get("temperature", 0.7)),
                top_p=float(style.prosody_plan.get("top_p", 0.9)),
            )
        else:
            speaker = self._SPEAKERS.get(voice.id, "Ryan")
            wavs, sr = model.generate_custom_voice(
                text=text, language=language_name, speaker=speaker, instruct=instruction,
                do_sample=True, temperature=float(style.prosody_plan.get("temperature", 0.7)),
                top_p=float(style.prosody_plan.get("top_p", 0.9)),
            )
        return wavs[0], int(sr)

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        prompt = text.strip()
        if not prompt:
            return
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("numpy is required for Qwen3-TTS") from exc
        waveform, sample_rate = self._generate(prompt, language, voice, style)
        pcm = np.asarray(waveform, dtype=np.float32).reshape(-1)
        pcm = np.clip(pcm, -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16).tobytes()
        packet_bytes = max(320, int(sample_rate * self.config.chunk_ms / 1000) * 2)
        for offset in range(0, len(pcm16), packet_bytes):
            yield TTSChunk(pcm16=pcm16[offset:offset + packet_bytes], sample_rate=sample_rate)
