from tom.voice.director import ConversationSignals, VoiceDirector
from tom.voice.models import Emotion
from tom.voice.session import VoiceSession
from tom.voice.tts_factory import HybridExpressiveTTS


class DummyEngine:
    def synthesize(self, text, *, language, voice, style):
        return b""


def test_default_character_is_tom_friendly_sigma():
    signals = ConversationSignals(user_text="hello")
    assert signals.character_name == "TOM"
    assert signals.character_style == "friendly"


def test_character_controls_override_base_delivery():
    style = VoiceDirector().direct(
        ConversationSignals(
            user_text="hello",
            character_name="Nova",
            character_style="calm analyst",
            character_traits=("calm", "precise"),
            character_pitch_shift=-0.3,
            character_speaking_rate=0.9,
            character_warmth=0.85,
            character_breathiness=0.4,
            character_expressiveness=0.55,
        )
    )
    assert style.pitch_shift == -0.3
    assert style.speaking_rate == 0.9
    assert style.warmth == 0.85
    assert style.breathiness == 0.4
    assert style.intensity == 0.55


def test_voice_session_keeps_character_metadata():
    session = VoiceSession(DummyEngine())
    turn = session.prepare_turn(
        "Okay, I am on it.",
        signals=ConversationSignals(
            user_text="Okay",
            character_name="Nova",
            character_style="calm analyst",
            character_traits=("calm", "precise"),
        ),
    )
    assert turn.style.prosody_plan["character"] == "Nova"
    assert turn.style.prosody_plan["character_style"] == "calm analyst"
    assert turn.style.prosody_plan["voice_design"] is True


def test_hybrid_backend_is_constructible_without_qwen_installed():
    assert isinstance(HybridExpressiveTTS(), HybridExpressiveTTS)
