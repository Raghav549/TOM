from tom.voice.director import ConversationSignals
from tom.voice.models import Language, VoiceProfile, VoiceStyle
from tom.voice.session import VoiceSession


class FakeStreamEngine:
    def stream(self, text, *, language, voice, style):
        assert text
        assert language is Language.EN
        assert voice.id == "tom_m1"
        yield type("Chunk", (), {"pcm16": b"\x00\x00" * 240, "sample_rate": 24000})()


def test_voice_session_keeps_stable_voice_design_off_by_default():
    turn = VoiceSession(FakeStreamEngine()).prepare_turn(
        "Hello bhai, this is TOM.",
        signals=ConversationSignals(
            user_text="Hello bhai, this is TOM.",
            character_name="TOM",
            character_style="friendly+sigma",
            character_traits=("warm", "confident"),
        ),
    )
    assert turn.language is Language.HINGLISH
    assert turn.style.prosody_plan["voice_design"] is False


def test_stream_only_engine_is_wrapped_as_valid_wav():
    session = VoiceSession(FakeStreamEngine())
    turn = session.prepare_turn("Hello.")
    audio = session.synthesize(turn)
    assert audio.startswith(b"RIFF")
    assert b"WAVE" in audio[:16]


def test_qwen_direct_backend_rejects_non_english_at_adapter_boundary():
    from tom.voice.qwen3_tts_stream import Qwen3TTSStreamingAdapter

    adapter = Qwen3TTSStreamingAdapter()
    style = VoiceStyle()
    voice = VoiceProfile(id="tom_m1", label="Tom M1", gender="male", description="test")
    try:
        next(adapter.stream("नमस्ते", language=Language.HI, voice=voice, style=style))
    except RuntimeError as exc:
        assert "Indic" in str(exc)
    else:
        raise AssertionError("Qwen backend must not silently accept an unsupported TOM language")
