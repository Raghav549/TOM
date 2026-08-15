from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SmartTurnDecision:
    complete_probability: float
    complete: bool


class SmartTurnONNX:
    """Open Smart Turn v3 ONNX endpoint detector.

    The model is the BSD-2-Clause Pipecat Smart Turn v3 family. It consumes
    16-kHz mono audio, pads/truncates to 8 seconds, computes Whisper-style
    log-mel features and runs the published ONNX classifier locally.
    """

    def __init__(self, model_path: str | None = None, threshold: float = 0.5) -> None:
        self.model_path = model_path or os.getenv("TOM_SMART_TURN_MODEL_PATH", "")
        self.threshold = float(os.getenv("TOM_SMART_TURN_THRESHOLD", str(threshold)))
        self._session = None

    @property
    def configured(self) -> bool:
        return bool(self.model_path)

    def _load(self):
        if self._session is not None:
            return self._session
        if not self.model_path:
            raise RuntimeError("TOM_SMART_TURN_MODEL_PATH is not configured")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("onnxruntime is required for Smart Turn ONNX") from exc
        self._session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        return self._session

    @staticmethod
    def _mel(audio):
        import numpy as np

        # Keep this implementation dependency-light; Pipecat's vendored feature
        # extractor can be selected through TOM_SMART_TURN_USE_PIPECAT=1.
        try:
            from pipecat.audio.turn.smart_turn._whisper_features import (
                compute_whisper_log_mel_features,
            )

            return compute_whisper_log_mel_features(audio, do_normalize=True)
        except ImportError:
            import librosa

            mel = librosa.feature.melspectrogram(
                y=audio, sr=16000, n_fft=400, hop_length=160, n_mels=80, fmin=0, fmax=8000
            )
            return np.log(np.maximum(mel, 1e-10)).astype(np.float32)

    def predict(self, pcm16: bytes, sample_rate: int = 16_000) -> SmartTurnDecision:
        if sample_rate != 16_000:
            raise ValueError("Smart Turn requires 16 kHz PCM16 audio")
        import numpy as np

        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        target = 8 * 16_000
        if audio.size > target:
            audio = audio[-target:]
        elif audio.size < target:
            audio = np.pad(audio, (target - audio.size, 0))
        features = self._mel(audio)
        if features.ndim == 2:
            features = features[None, ...]
        output = self._load().run(None, {"input_features": features})[0]
        probability = float(np.asarray(output).reshape(-1)[0])
        return SmartTurnDecision(probability, probability >= self.threshold)
