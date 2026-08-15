from __future__ import annotations

import itertools
import math
import re
import struct
from dataclasses import dataclass

@dataclass(frozen=True)
class AcousticFrame:
    rms: float
    pitch_hz: float | None
    pitch_confidence: float
    zero_crossing_rate: float

@dataclass(frozen=True)
class UserProsody:
    mean_pitch_hz: float | None
    pitch_range_hz: float
    energy: float
    energy_variation: float
    pitch_variation: float
    speech_rate_proxy: float
    pitch_confidence: float
    likely_question: bool
    likely_excited: bool
    likely_tired_or_calm: bool

@dataclass(frozen=True)
class SpeechCue:
    kind: str
    position: int
    duration_ms: int = 0
    strength: float = 0.0

@dataclass(frozen=True)
class ExpressivePlan:
    cues: tuple[SpeechCue, ...]
    pitch_curve: tuple[float, ...]
    energy_curve: tuple[float, ...]
    rate_curve: tuple[float, ...]
    rationale: tuple[str, ...]


def _pitch_autocorrelation(samples: list[float], sample_rate: int) -> tuple[float | None, float]:
    if len(samples) < 64:
        return None, 0.0
    mean = sum(samples) / len(samples)
    x = [s - mean for s in samples]
    energy = sum(v * v for v in x)
    if energy <= 1e-8:
        return None, 0.0
    min_lag = max(1, int(sample_rate / 450.0))
    max_lag = min(len(x) - 2, int(sample_rate / 70.0))
    best_lag = 0
    best = -1.0
    for lag in range(min_lag, max_lag + 1):
        corr = sum(x[i] * x[i + lag] for i in range(len(x) - lag))
        norm = math.sqrt(energy * sum(v * v for v in x[lag:]))
        score = corr / norm if norm else 0.0
        if score > best:
            best, best_lag = score, lag
    if best_lag == 0 or best < 0.35:
        return None, max(0.0, best)
    return sample_rate / best_lag, min(1.0, max(0.0, best))


def _frame(samples: list[float], sample_rate: int) -> AcousticFrame:
    if not samples:
        return AcousticFrame(0.0, None, 0.0, 0.0)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    zc = sum(1 for a, b in itertools.pairwise(samples) if (a < 0) != (b < 0)) / max(1, len(samples) - 1)
    pitch, confidence = _pitch_autocorrelation(samples, sample_rate)
    return AcousticFrame(rms, pitch, confidence, zc)


class PCM16ProsodyExtractor:
    """Dependency-light acoustic feature extractor for live PCM16 mono audio."""

    def analyze(self, pcm16: bytes, sample_rate: int = 16_000) -> UserProsody:
        if not pcm16 or len(pcm16) < 4:
            return UserProsody(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, False, False)
        count = len(pcm16) // 2
        values = struct.unpack("<" + "h" * count, pcm16[: count * 2])
        samples = [v / 32768.0 for v in values]
        frame_size = max(160, int(sample_rate * 0.04))
        frames = [_frame(samples[i : i + frame_size], sample_rate) for i in range(0, len(samples), frame_size)]
        voiced = [f for f in frames if f.pitch_hz is not None and f.pitch_confidence >= 0.45]
        pitches = [f.pitch_hz for f in voiced if f.pitch_hz is not None]
        energies = [f.rms for f in frames]
        mean_pitch = sum(pitches) / len(pitches) if pitches else None
        pitch_range = max(pitches) - min(pitches) if pitches else 0.0
        energy = sum(energies) / len(energies) if energies else 0.0
        energy_var = math.sqrt(sum((x - energy) ** 2 for x in energies) / len(energies)) if energies else 0.0
        pitch_var = math.sqrt(sum((x - mean_pitch) ** 2 for x in pitches) / len(pitches)) if pitches and mean_pitch else 0.0
        voiced_ratio = len(voiced) / max(1, len(frames))
        speech_rate_proxy = voiced_ratio * (1.0 + min(1.0, pitch_var / 60.0))
        confidence = sum(f.pitch_confidence for f in voiced) / len(voiced) if voiced else 0.0
        return UserProsody(
            mean_pitch_hz=mean_pitch,
            pitch_range_hz=pitch_range,
            energy=energy,
            energy_variation=energy_var,
            pitch_variation=pitch_var,
            speech_rate_proxy=speech_rate_proxy,
            pitch_confidence=confidence,
            likely_question=False,
            likely_excited=pitch_var > 35.0 and energy_var > 0.035,
            likely_tired_or_calm=pitch_var < 10.0 and energy_var < 0.012 and voiced_ratio > 0.25,
        )


class ExpressiveSpeechPlanner:
    """Converts semantic text + voice style into non-random expressive cues."""

    _filler_after = re.compile(r"\b(so|well|actually|acha|accha|haan|dekho|मतलब|अच्छा)\b", re.IGNORECASE)
    _question = re.compile(r"[?？]$")
    _strong = re.compile(r"[!！]+")

    def plan(self, text: str, *, emotion: str, intensity: float, speaking_rate: float, warmth: float) -> ExpressivePlan:
        cues: list[SpeechCue] = []
        rationale: list[str] = []
        for match in self._filler_after.finditer(text):
            if match.start() > 0:
                cues.append(SpeechCue("micro_pause", match.start(), 90, 0.35))
        for match in re.finditer(r"[,;:—-]", text):
            cues.append(SpeechCue("phrase_pause", match.end(), 130, 0.45))
        for match in re.finditer(r"[.!?।!?]", text):
            cues.append(SpeechCue("sentence_pause", match.end(), 210 if match.group() in ".।" else 160, 0.65))
        if self._question.search(text.strip()):
            rationale.append("question contour: final pitch lift")
        if self._strong.search(text):
            rationale.append("emphasis contour: energy lift around exclamatory phrase")
        if emotion in {"empathetic", "concerned", "calm"}:
            cues.append(SpeechCue("soft_breath", 0, 260, min(0.75, 0.35 + warmth * 0.35)))
            rationale.append("emotion requires slower, warmer delivery")
        if emotion in {"amused", "happy", "excited"} and intensity > 0.55:
            cues.append(SpeechCue("smile_voice", 0, 0, intensity))
            rationale.append("positive affect: brighter energy without forced laughter")
        if emotion in {"warm", "empathetic", "concerned"} and warmth > 0.7:
            cues.append(SpeechCue("backchannel_candidate", 0, 0, warmth))
        n = max(4, min(24, len(text) // 18 + 4))
        base_pitch = 0.10 if emotion in {"happy", "amused", "excited"} else -0.04 if emotion in {"concerned", "sad", "calm"} else 0.0
        denominator = max(1, n - 1)
        pitch = tuple(base_pitch + (0.06 * math.sin(i / denominator * math.pi * 2)) * intensity for i in range(n))
        energy = tuple(max(0.0, min(1.0, 0.35 + intensity * 0.45 + 0.08 * math.sin(i / denominator * math.pi))) for i in range(n))
        rate = tuple(max(0.65, min(1.35, speaking_rate * (1.0 - 0.04 * math.sin(i / denominator * math.pi))) for i in range(n))
        return ExpressivePlan(tuple(sorted(cues, key=lambda c: c.position)), pitch, energy, rate, tuple(rationale))
