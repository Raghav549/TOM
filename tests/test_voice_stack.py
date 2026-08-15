import pytest

from tom.voice.director import ConversationSignals, VoiceDirector
from tom.voice.engine import ExternalCommandSpeechEngine, SpeechEngineConfig
from tom.voice.models import VOICE_PROFILES, Emotion, Language
from tom.voice.session import VoiceSession


def test_language_routing():
    director = VoiceDirector()
    assert director.detect_language("नमस्ते, कैसे हो?") is Language.HI
    assert director.detect_language("How are you today?") is Language.EN
    assert director.detect_language("Bhai aaj kya scene hai?") is Language.HINGLISH
    assert director.detect_language("তুমি কেমন আছো?") is Language.BN


def test_three_distinct_voice_profiles():
    assert set(VOICE_PROFILES) == {"tom_m1", "tom_m2", "tom_f1"}
    assert len({p.description for p in VOICE_PROFILES.values()}) == 3


def test_emotion_director_is_context_sensitive():
    director = VoiceDirector()
    sad = director.direct(ConversationSignals(user_text="I am really sad today", user_is_sad=True))
    success = director.direct(ConversationSignals(task_succeeded=True))
    running = director.direct(ConversationSignals(task_running=True))
    assert sad.emotion is Emotion.EMPATHETIC
    assert success.emotion is Emotion.HAPPY
    assert running.backchannel is True
    assert sad.speaking_rate < success.speaking_rate


def test_no_fake_audio_when_engine_missing():
    engine = ExternalCommandSpeechEngine(SpeechEngineConfig(command=None))
    session = VoiceSession(engine)
    turn = session.prepare_turn("Bhai, ho gaya!", voice_id="tom_m1")
    with pytest.raises(RuntimeError, match="TOM_TTS_COMMAND"):
        session.synthesize(turn)
