from tom.voice.prosody import ExpressiveSpeechPlanner, PCM16ProsodyExtractor
from tom.voice.turntaking import DuplexState, DuplexTurnManager, TurnSignal


def test_expressive_planner_creates_contextual_cues():
    plan = ExpressiveSpeechPlanner().plan(
        "Bhai, ye ho gaya! Really?",
        emotion="happy",
        intensity=0.75,
        speaking_rate=1.0,
        warmth=0.8,
    )
    assert plan.cues
    assert len(plan.pitch_curve) >= 4
    assert len(plan.energy_curve) == len(plan.rate_curve)
    assert any("positive affect" in x for x in plan.rationale)


def test_silence_is_safe_for_prosody_extractor():
    result = PCM16ProsodyExtractor().analyze(b"\x00\x00" * 16000)
    assert result.mean_pitch_hz is None
    assert result.energy == 0.0


def test_duplex_barge_in_stops_tom():
    manager = DuplexTurnManager()
    decision = manager.update(
        TurnSignal(
            user_voice_active=True,
            user_voice_duration_ms=260,
            user_speech_confidence=0.9,
            user_started_while_tom_speaking=True,
        ),
        tom_speaking=True,
    )
    assert decision.state is DuplexState.OVERLAP
    assert decision.stop_tom_audio is True
    assert decision.yield_to_user is True


def test_duplex_waits_for_stable_resume_boundary():
    manager = DuplexTurnManager()
    manager.update(
        TurnSignal(user_voice_active=True, user_voice_duration_ms=250, user_speech_confidence=0.9),
        tom_speaking=True,
    )
    waiting = manager.update(
        TurnSignal(user_voice_active=False, user_stopped_ms_ago=100),
        tom_speaking=False,
    )
    assert waiting.resume_allowed is False
    resumed = manager.update(
        TurnSignal(user_voice_active=False, user_stopped_ms_ago=500),
        tom_speaking=False,
    )
    assert resumed.resume_allowed is True
