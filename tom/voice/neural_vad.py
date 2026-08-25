from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VADDecision:
    speech_probability: float
    speech: bool
    start: bool
    end: bool


class SileroStreamingVAD:
    """Streaming 16 kHz PCM16 VAD with a lightweight fallback.

    Silero is used when installed. Production web services that deliberately
    omit the heavy neural extra still get a real energy-based VAD instead of
    dropping every voice turn or closing the websocket.
    """

    def __init__(self, threshold: float | None = None, min_speech_ms: int = 160, min_silence_ms: int = 420) -> None:
        self.threshold = threshold if threshold is not None else float(os.getenv("TOM_VAD_THRESHOLD", "0.55"))
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self._model = None
        self._fallback = False
        self._pending = bytearray()
        self._speech_ms = 0
        self._silence_ms = 0
        self._in_speech = False

    def _load(self) -> None:
        if self._model is not None or self._fallback:
            return
        try:
            from silero_vad import load_silero_vad
        except ImportError:
            # Render's lightweight voice build does not install Torch/Silero.
            # Keep the protocol alive with deterministic energy VAD.
            self._fallback = True
            return
        self._model = load_silero_vad()

    def reset(self) -> None:
        self._pending.clear()
        self._speech_ms = 0
        self._silence_ms = 0
        self._in_speech = False
        if self._model is not None and hasattr(self._model, "reset_states"):
            self._model.reset_states()

    def _update_state(self, probability: float, frame_ms: int) -> tuple[bool, bool]:
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
        return start, end

    @staticmethod
    def _fallback_probability(audio) -> float:
        # RMS energy normalized into a VAD-like 0..1 score. The scale is kept
        # configurable because microphone gain differs across Android devices.
        import numpy as np

        rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64))) if audio.size else 0.0
        scale = max(0.001, float(os.getenv("TOM_FALLBACK_VAD_RMS", "0.04")))
        return max(0.0, min(1.0, rms / scale))

    def process(self, pcm16: bytes, sample_rate: int = 16_000) -> VADDecision:
        if sample_rate != 16_000:
            raise ValueError("SileroStreamingVAD requires 16 kHz PCM16 audio")
        if not pcm16:
            return VADDecision(0.0, self._in_speech, False, False)
        self._load()
        import numpy as np

        torch = None
        if not self._fallback:
            import torch as _torch
            torch = _torch

        self._pending.extend(pcm16)
        frame_bytes = 512 * 2
        probabilities: list[float] = []
        start = False
        end = False
        while len(self._pending) >= frame_bytes:
            frame = bytes(self._pending[:frame_bytes])
            del self._pending[:frame_bytes]
            audio = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
            if self._fallback:
                probability = self._fallback_probability(audio)
            else:
                probability = float(self._model(torch.from_numpy(audio), 16_000).item())
            probabilities.append(probability)
            frame_start, frame_end = self._update_state(probability, 32)
            start = start or frame_start
            end = end or frame_end
        probability = probabilities[-1] if probabilities else (self.threshold if self._in_speech else 0.0)
        return VADDecision(probability, self._in_speech, start, end)
