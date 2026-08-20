import pytest
from fastapi import HTTPException

from tom.voice import qwen3_tts_service as service


def test_qwen3_public_endpoint_requires_token_in_production(monkeypatch):
    monkeypatch.setenv("TOM_ENV", "production")
    monkeypatch.setenv("TOM_QWEN3_TTS_AUTH_TOKEN", "secret-token")

    with pytest.raises(HTTPException) as exc:
        service._authorize("wrong-token")
    assert exc.value.status_code == 401

    service._authorize("secret-token")


def test_qwen3_auth_is_not_required_for_local_development(monkeypatch):
    monkeypatch.setenv("TOM_ENV", "development")
    monkeypatch.delenv("TOM_QWEN3_TTS_AUTH_TOKEN", raising=False)
    service._authorize(None)


def test_qwen3_requires_auth_configuration_for_production(monkeypatch):
    monkeypatch.setenv("TOM_ENV", "production")
    monkeypatch.delenv("TOM_QWEN3_TTS_AUTH_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        service._authorize(None)
    assert exc.value.status_code == 503


def test_qwen3_frame_has_type_and_big_endian_length():
    frame = service._frame(0, b"abcd")
    assert frame == b"\x00\x00\x00\x00\x04abcd"
