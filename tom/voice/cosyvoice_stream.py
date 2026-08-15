from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

from .models import Language, VoiceProfile, VoiceStyle


@dataclass(frozen=True)
class TTSChunk:
    pcm16: bytes
    sample_rate: int


class CosyVoiceStreamingAdapter:
    """Real CosyVoice2/3 streaming adapter with lazy heavy imports."""

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir or os.getenv("TOM_COSYVOICE_MODEL_DIR", "")
        self._model = None
        self._sample_rate = 24000

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.model_dir:
            raise RuntimeError("TOM_COSYVOICE_MODEL_DIR is not configured")
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2
        except ImportError as exc:
            raise RuntimeError(
                "CosyVoice is not installed. Install the official CosyVoice runtime first."
            ) from exc
        self._model = CosyVoice2(self.model_dir, load_jit=True, fp16=True)
        self._sample_rate = int(self._model.sample_rate)
        return self._model

    @staticmethod
    def _ref_audio(voice: VoiceProfile) -> str:
        if voice.reference_audio:
            return voice.reference_audio
        env_key = f"TOM_COSYVOICE_REF_{voice.id.upper()}"
        value = os.getenv(env_key, "").strip()
        if not value:
            raise RuntimeError(f"No reference audio configured for {voice.id} ({env_key})")
        return value

    @staticmethod
    def _instruction(style: VoiceStyle) -> str:
        return (
            f"Speak naturally and conversationally. Emotion: {style.emotion.value}. "
            f"Intensity: {style.intensity:.2f}. Warmth: {style.warmth:.2f}. "
            f"Speaking rate: {style.speaking_rate:.2f}. "
            "Use natural pauses and sentence-final prosody; never add random laughter or fillers."
        )

    def stream(
        self,
        text: str,
        *,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> Iterator[TTSChunk]:
        import numpy as np

        model = self._load()
        ref_path = self._ref_audio(voice)
        try:
            from cosyvoice.utils.file_utils import load_wav
        except ImportError as exc:
            raise RuntimeError("CosyVoice load_wav helper is unavailable") from exc

        prompt_speech_16k = load_wav(ref_path, 16000)
        outputs = model.inference_instruct2(
            text,
            self._instruction(style),
            prompt_speech_16k,
            stream=True,
            speed=style.speaking_rate,
            text_frontend=True,
        )
        for output in outputs:
            tensor = output["tts_speech"]
            if hasattr(tensor, "detach"):
                audio = tensor.detach().float().cpu().numpy()
            else:
                audio = np.asarray(tensor, dtype=np.float32)
            audio = np.squeeze(audio)
            pcm = np.clip(audio, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype(np.int16).tobytes()
            if pcm:
                yield TTSChunk(pcm16=pcm, sample_rate=self._sample_rate)
