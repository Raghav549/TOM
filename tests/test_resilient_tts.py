from tom.voice.resilient_tts import ResilientTTS
from tom.voice.models import VOICE_PROFILES, Language, VoiceStyle


class FakePrimary:
    def stream(self, *args, **kwargs):
        raise RuntimeError("primary unavailable")


class FakeFallback:
    def stream(self, *args, **kwargs):
        from tom.voice.cosyvoice_stream import TTSChunk
        yield TTSChunk(pcm16=b"fallback", sample_rate=24_000)


def test_resilient_tts_falls_back_without_fake_success(monkeypatch):
    engine = ResilientTTS.__new__(ResilientTTS)
    engine.primary = FakePrimary()
    engine.fallback = FakeFallback()
    chunks = list(engine.stream("hello", language=Language.HI, voice=VOICE_PROFILES["tom_m1"], style=VoiceStyle()))
    assert chunks[0].pcm16 == b"fallback"
    assert engine.last_backend == "indic-parler"
