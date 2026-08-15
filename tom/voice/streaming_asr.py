from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PartialTranscript:
    text: str
    confidence: float
    language: str | None
    is_final: bool = False


class StreamingFasterWhisper:
    """Incremental ASR over a rolling PCM window."""

    def __init__(self) -> None:
        self.model_name = os.getenv("TOM_ASR_MODEL", "small")
        self.device = os.getenv("TOM_ASR_DEVICE", "cuda")
        self.compute_type = os.getenv("TOM_ASR_COMPUTE_TYPE", "float16")
        self.partial_interval_ms = int(os.getenv("TOM_ASR_PARTIAL_INTERVAL_MS", "480"))
        self.context_ms = int(os.getenv("TOM_ASR_CONTEXT_MS", "3200"))
        self._model = None
        self._buffer = bytearray()
        self._elapsed_ms = 0
        self._last_text = ""

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is not installed") from exc
        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model

    @staticmethod
    def _decode(model, pcm16: bytes) -> PartialTranscript:
        if not pcm16:
            return PartialTranscript("", 0.0, None)
        import numpy as np

        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = model.transcribe(
            audio, beam_size=1, vad_filter=False, condition_on_previous_text=False, without_timestamps=True
        )
        parts: list[str] = []
        confidence: list[float] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)
            confidence.append(max(0.0, min(1.0, float(segment.avg_logprob + 1.0))))
        return PartialTranscript(" ".join(parts), sum(confidence) / len(confidence) if confidence else 0.0, getattr(info, "language", None))

    def reset(self) -> None:
        self._buffer.clear()
        self._elapsed_ms = 0
        self._last_text = ""

    def push(self, pcm16: bytes, sample_rate: int = 16_000) -> PartialTranscript | None:
        if sample_rate != 16_000:
            raise ValueError("StreamingFasterWhisper requires 16 kHz audio")
        self._buffer.extend(pcm16)
        self._elapsed_ms += int(len(pcm16) / 2 * 1000 / sample_rate)
        if self._elapsed_ms < self.partial_interval_ms:
            return None
        self._elapsed_ms = 0
        max_bytes = int(self.context_ms / 1000 * sample_rate) * 2
        result = self._decode(self._load(), bytes(self._buffer[-max_bytes:]))
        if result.text == self._last_text:
            return None
        self._last_text = result.text
        return result

    def final(self, sample_rate: int = 16_000) -> PartialTranscript:
        if sample_rate != 16_000:
            raise ValueError("StreamingFasterWhisper requires 16 kHz audio")
        result = self._decode(self._load(), bytes(self._buffer))
        return PartialTranscript(result.text, result.confidence, result.language, True)
