from tom.voice.models import Language, VoiceProfile, VoiceStyle
from tom.voice.qwen3_tts_stream import Qwen3TTSStreamingAdapter, Qwen3VoiceConfig


class FakeModel:
    def generate_custom_voice(self, *args, **kwargs):
        import numpy as np
        assert kwargs["text"] == "hello"
        assert kwargs["speaker"] == "Ryan"
        return [np.zeros(24000, dtype=np.float32)], 24000


def test_qwen_chunks_real_generation_output_without_model_streaming(monkeypatch):
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

    assert len(chunks) > 1
    assert all(chunk.sample_rate == 24000 for chunk in chunks)
    assert all(len(chunk.pcm16) > 0 and len(chunk.pcm16) % 2 == 0 for chunk in chunks)


def test_float_audio_is_converted_to_int16():
    import pytest

    np = pytest.importorskip("numpy")
    pcm = Qwen3TTSStreamingAdapter._to_pcm16_bytes(np.array([-1.0, 0.0, 1.0], dtype=np.float32))
    values = np.frombuffer(pcm, dtype=np.int16)
    assert values.tolist() == [-32767, 0, 32767]
