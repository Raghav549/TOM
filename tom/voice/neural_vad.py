from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VADDecision:
    speech_probability: float
    speech: bool
    start: bool
    end: bool


class SileroStreamingVAD:
    """Real Silero VAD state machine for 16 kHz PCM16 streams.

    The model is loaded lazily. There is deliberately no fake neural fallback:
    if neural VAD is enabled but unavailable, the runtime reports the error.
    """

    def __init__(
        self,
        threshold: float | None = None,
        min_speech_ms: int = 160,
        min_silence_ms: int = 420,
    ) -> None:
        self.threshold = threshold if threshold is not None else float(os.getenv("TOM_VAD_THRESHOLD", "0.55"))
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self._model = None
        self._state = None
        self._speech_ms = 0
        self._silence_ms = 0
        self._in_speech = False

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from silero_vad import load_silero_vad
        except ImportError as exc:
            raise RuntimeError(
                "Silero VAD is not installed. Install TOM with '.[voice-neural]'."
            ) from exc
        self._model = load_silero_vad()

    def reset(self) -> None:
        self._speech_ms = 0
        self._silence_ms = 0
        self._in_speech = False
        self._state = None

    def process(self, pcm16: bytes, sample_rate: int = 16_000) -> VADDecision:
        if sample_rate != 16_000:
            raise ValueError("SileroStreamingVAD requires 16 kHz PCM16 audio")
        if not pcm16:
            return VADDecision(0.0, self._in_speech, False, False)
        self._load()
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return VADDecision(0.0, self._in_speech, False, False)
        import torch

        tensor = torch.from_numpy(audio)
        probability = float(self._model(tensor, 16_000).item())
        frame_ms = max(1, int(audio.size * 1000 / sample_rate))
        start = False
        end = False
        if probability >= self.threshold:
            self._speech_ms += frame_ms
            self._silence_ms = 0
            if not self._in_speech and self._speech_ms >= self.min_speech_ms:
                self._in_speech = True
                start = True
        else:
            self._silence_ms += frame_ms
            if self._in_speech and self._silence_ms >= self.min_silence_ms:
                self._in_speech = False
                self._speech_ms = 0
                self._silence_ms = 0
                end = True
        return VADDecision(probability, self._in_speech, start, end)
