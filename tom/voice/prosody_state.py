from __future__ import annotations

from dataclasses import dataclass

from .prosody import PCM16ProsodyExtractor, UserProsody


@dataclass(frozen=True)
class ContinuousProsodyState:
    mean_pitch_hz: float | None
    pitch_variation: float
    energy: float
    energy_variation: float
    speech_rate: float
    arousal: float
    valence_hint: float
    confidence: float


class ContinuousProsodyTracker:
    """Low-latency EMA over acoustic emotion/prosody features."""

    def __init__(self, alpha: float = 0.24) -> None:
        self.alpha = alpha
        self.extractor = PCM16ProsodyExtractor()
        self._state = ContinuousProsodyState(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def state(self) -> ContinuousProsodyState:
        return self._state

    def reset(self) -> None:
        self._state = ContinuousProsodyState(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def update(self, pcm16: bytes, sample_rate: int = 16_000) -> ContinuousProsodyState:
        current: UserProsody = self.extractor.analyze(pcm16, sample_rate)
        old = self._state

        def ema(previous: float, value: float) -> float:
            return previous * (1.0 - self.alpha) + value * self.alpha

        pitch = current.mean_pitch_hz if current.mean_pitch_hz is not None else old.mean_pitch_hz
        self._state = ContinuousProsodyState(
            pitch,
            ema(old.pitch_variation, current.pitch_variation),
            ema(old.energy, current.energy),
            ema(old.energy_variation, current.energy_variation),
            ema(old.speech_rate, current.speech_rate_proxy),
            ema(old.arousal, min(1.0, current.pitch_variation / 70.0 * 0.55 + current.energy * 1.8)),
            ema(old.valence_hint, 0.35 if current.likely_excited else -0.15 if current.likely_tired_or_calm else 0.0),
            ema(old.confidence, current.pitch_confidence),
        )
        return self._state
