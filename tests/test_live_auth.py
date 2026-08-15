import base64
import json

from tom.bridge.live_auth import LiveAuthConfig, LiveDeviceAuthenticator


def test_device_secret_challenge_proof():
    secret = b"x" * 32
    auth = LiveDeviceAuthenticator(LiveAuthConfig({"phone-1": secret}))
    issued = auth.challenge_session("phone-1")
    assert issued is not None
    challenge, session = issued

    import hashlib
    import hmac
    proof = hmac.new(secret, challenge.encode(), hashlib.sha256).hexdigest()
    assert auth.verify("phone-1", challenge, proof)
    assert not auth.verify("phone-1", challenge, "bad")
    assert auth.challenge_session("unknown") is None


def test_environment_secret_requires_32_bytes(monkeypatch):
    raw = base64.b64encode(b"short").decode()
    monkeypatch.setenv("TOM_DEVICE_SECRETS_JSON", json.dumps({"phone-1": raw}))
    try:
        LiveAuthConfig.from_environment()
    except ValueError as exc:
        assert "32 bytes" in str(exc)
    else:
        raise AssertionError("short device secret was accepted")
