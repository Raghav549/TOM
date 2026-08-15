from tom.voice.indic_parler_stream import IndicParlerStreamingAdapter
from tom.voice.models import VOICE_PROFILES, Language, VoiceStyle
from tom.voice.smart_turn_onnx import SmartTurnONNX


def test_three_tom_voice_identities_are_distinct():
    assert list(VOICE_PROFILES) == ["tom_m1", "tom_m2", "tom_f1"]
    assert len({v.gender for v in VOICE_PROFILES.values()}) == 2


def test_indic_parler_language_speaker_mapping():
    adapter = IndicParlerStreamingAdapter()
    assert adapter._speaker_for(Language.HI, adapter.VOICES["tom_m1"]) == "Rohit"
    assert adapter._speaker_for(Language.HI, adapter.VOICES["tom_f1"]) == "Divya"
    assert adapter._speaker_for(Language.BN, adapter.VOICES["tom_m1"]) == "Arjun"
    assert adapter._speaker_for(Language.EN, adapter.VOICES["tom_f1"]) == "Mary"


def test_indic_parler_description_contains_conversational_controls():
    adapter = IndicParlerStreamingAdapter()
    description = adapter._description(
        VOICE_PROFILES["tom_m1"], Language.HI, VoiceStyle(speaking_rate=0.82)
    )
    assert "Rohit" in description
    assert "slow" in description
    assert "natural pauses" in description
    assert "conversational" in description


def test_smart_turn_requires_explicit_model_path():
    assert not SmartTurnONNX(model_path="").configured
