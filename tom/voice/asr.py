from __future__ import annotations

import os
import tempfile
import wave


class FasterWhisperASR:
    """Real local ASR adapter for completed voice turns.

    Uses faster-whisper when installed. The model is loaded lazily so TOM's
    normal text runtime does not pay the GPU/model startup cost.
    """

    def __init__(self) -> None:
        self.model_name = os.getenv("TOM_ASR_MODEL", "small")
        self.device = os.getenv("TOM_ASR_DEVICE", "cuda")
        self.compute_type = os.getenv("TOM_ASR_COMPUTE_TYPE", "float16")
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed; install it before starting the live voice loop."
            ) from exc
        try:
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as exc:
            raise RuntimeError(f"ASR model failed to load: {exc}") from exc
        return self._model

    @staticmethod
    def _wav(pcm16: bytes, sample_rate: int) -> str:
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        handle.close()
        with wave.open(handle.name, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(sample_rate)
            out.writeframes(pcm16)
        return handle.name

    def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> tuple[str, float, str | None]:
        if not pcm16:
            return "", 0.0, None
        path = self._wav(pcm16, sample_rate)
        try:
            segments, info = self._load().transcribe(
                path,
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            parts: list[str] = []
            confidences: list[float] = []
            for segment in segments:
                parts.append(segment.text.strip())
                confidences.append(max(0.0, min(1.0, float(segment.avg_logprob + 1.0))))
            text = " ".join(p for p in parts if p)
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
            language = getattr(info, "language", None)
            return text, confidence, language
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
