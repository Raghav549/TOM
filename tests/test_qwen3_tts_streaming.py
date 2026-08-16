from tom.voice.models import Language, VoiceProfile, VoiceStyle
from tom.voice.qwen3_tts_stream import Qwen3TTSStreamingAdapter, Qwen3VoiceConfig


class FakeModel:
    def stream_generate_custom_voice(self, **kwargs):
        assert kwargs["text"] == "hello"
        assert kwargs["speaker"] == "Ryan"
        assert kwargs["emit_every_frames"] == 4
        assert kwargs["decode_window_frames"] == 72
        yield b"first", 24000
        yield b"second", 24000


def test_qwen_streams_model_chunks_without_full_generation(monkeypatch):
    adapter = Qwen3TTSStreamingAdapter(
        Qwen3VoiceConfig(
            streaming=True,
            emit_every_frames=4,
            decode_window_frames=72,
            first_chunk_emit_every=5,
            first_chunk_frames=24,
            attn_implementation=None,
        )
    )
    fake = FakeModel()
    monkeypatch.setattr(adapter, "_load", lambda design=False: fake)

    voice = VoiceProfile(id="tom_m1", label="TOM", gender="male", description="test")
    chunks = list(adapter.stream("hello", language=Language.EN, voice=voice, style=VoiceStyle()))

    assert [c.pcm16 for c in chunks] == [b"first", b"second"]
    assert [c.sample_rate for c in chunks] == [24000, 24000]


def test_float_audio_is_converted_to_int16():
    import numpy as np

    pcm = Qwen3TTSStreamingAdapter._to_pcm16_bytes(np.array([-1.0, 0.0, 1.0], dtype=np.float32))
    values = np.frombuffer(pcm, dtype=np.int16)
    assert values.tolist() == [-32767, 0, 32767]
