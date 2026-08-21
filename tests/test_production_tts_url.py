import pytest

from tom.production import _qwen3_health_url


@pytest.mark.parametrize(
    ("stream_url", "expected"),
    [
        (
            "https://example.trycloudflare.com/v1/tts/qwen3/stream",
            "https://example.trycloudflare.com/v1/tts/qwen3/health",
        ),
        (
            "https://example.trycloudflare.com/v1/tts/qwen3/stream/secret-token",
            "https://example.trycloudflare.com/v1/tts/qwen3/health",
        ),
        (
            "https://example.trycloudflare.com/prefix/v1/tts/qwen3/stream/secret-token?x=1",
            "https://example.trycloudflare.com/prefix/v1/tts/qwen3/health",
        ),
    ],
)
def test_qwen3_health_url_handles_plain_and_tokenized_stream_urls(stream_url, expected):
    assert _qwen3_health_url(stream_url) == expected


def test_qwen3_health_url_rejects_invalid_url():
    with pytest.raises(ValueError):
        _qwen3_health_url("not-a-url")
