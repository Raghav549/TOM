from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TurnPrediction:
    end_probability: float
    interrupt_probability: float
    continue_probability: float


class LearnedTurnPredictor:
    """ONNX learned turn-taking model adapter.

    Expected model input: float32 [1, 8] containing
    [vad, vad_delta, energy, energy_delta, pitch_variation,
     speech_rate, asr_confidence, tom_speaking].
    Expected output: float32 [1, 3] probabilities ordered as
    [continue, end, interrupt].

    No synthetic prediction is returned when a model path is configured but
    unavailable. Until a trained checkpoint is supplied, the existing
    DuplexTurnManager remains the deterministic safety controller.
    """

    def __init__(self) -> None:
        self.model_path = os.getenv("TOM_TURN_MODEL_PATH", "").strip()
        self._session = None
        self._input_name = None

    @property
    def configured(self) -> bool:
        return bool(self.model_path)

    def _load(self) -> None:
        if self._session is not None:
            return
        if not self.model_path:
            raise RuntimeError("TOM_TURN_MODEL_PATH is not configured")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("onnxruntime is not installed; install '.[voice-neural]'") from exc
        self._session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def predict(
        self,
        *,
        vad: float,
        vad_delta: float,
        energy: float,
        energy_delta: float,
        pitch_variation: float,
        speech_rate: float,
        asr_confidence: float,
        tom_speaking: bool,
    ) -> TurnPrediction:
        self._load()
        features = np.asarray(
            [[
                vad,
                vad_delta,
                energy,
                energy_delta,
                pitch_variation,
                speech_rate,
                asr_confidence,
                1.0 if tom_speaking else 0.0,
            ]],
            dtype=np.float32,
        )
        output = np.asarray(self._session.run(None, {self._input_name: features})[0]).reshape(-1)
        if output.size != 3:
            raise RuntimeError("TOM turn model must return exactly 3 probabilities")
        values = np.clip(output, 0.0, 1.0)
        total = float(values.sum())
        if total <= 0:
            raise RuntimeError("TOM turn model returned invalid probabilities")
        values = values / total
        return TurnPrediction(float(values[1]), float(values[2]), float(values[0]))
