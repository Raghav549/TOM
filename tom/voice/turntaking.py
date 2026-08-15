from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DuplexState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    OVERLAP = "overlap"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class TurnSignal:
    user_voice_active: bool
    user_voice_duration_ms: int = 0
    user_speech_confidence: float = 0.0
    user_started_while_tom_speaking: bool = False
    user_stopped_ms_ago: int = 0
    explicit_interrupt: bool = False


@dataclass(frozen=True)
class TurnDecision:
    state: DuplexState
    stop_tom_audio: bool
    yield_to_user: bool
    resume_allowed: bool
    reason: str


class DuplexTurnManager:
    """Deterministic barge-in controller for full-duplex voice.

    It treats sustained user speech as stronger evidence than a single noisy
    VAD frame, while allowing immediate explicit interruption. A learned turn
    predictor can later provide probabilities without changing this contract.
    """

    def __init__(self, min_user_speech_ms: int = 180, resume_silence_ms: int = 420) -> None:
        self.min_user_speech_ms = min_user_speech_ms
        self.resume_silence_ms = resume_silence_ms
        self.state = DuplexState.IDLE

    def update(self, signal: TurnSignal, *, tom_speaking: bool) -> TurnDecision:
        if signal.explicit_interrupt:
            self.state = DuplexState.INTERRUPTED
            return TurnDecision(self.state, True, True, False, "explicit user interruption")
        if tom_speaking and signal.user_voice_active:
            if signal.user_voice_duration_ms >= self.min_user_speech_ms and signal.user_speech_confidence >= 0.55:
                self.state = DuplexState.OVERLAP
                return TurnDecision(self.state, True, True, False, "sustained high-confidence barge-in")
            self.state = DuplexState.SPEAKING
            return TurnDecision(self.state, False, False, False, "possible overlap; hold briefly")
        if self.state in {DuplexState.INTERRUPTED, DuplexState.OVERLAP}:
            if not signal.user_voice_active and signal.user_stopped_ms_ago >= self.resume_silence_ms:
                self.state = DuplexState.LISTENING
                return TurnDecision(self.state, False, True, True, "user turn appears complete")
            return TurnDecision(self.state, False, True, False, "waiting for stable turn boundary")
        if signal.user_voice_active:
            self.state = DuplexState.LISTENING
            return TurnDecision(self.state, False, True, False, "user is speaking")
        self.state = DuplexState.IDLE
        return TurnDecision(self.state, False, False, False, "no active turn")
