import pytest

from tom.transport.protocol import BridgeMessage, MessageType
from tom.transport.router import TransportRouter
from tom.transport.session import DeviceSession, SessionState


def message(sequence: int, device_id: str = "device-1") -> BridgeMessage:
    return BridgeMessage(
        id=f"m-{sequence}",
        type=MessageType.HEARTBEAT,
        timestamp_ms=1,
        payload={"device_id": device_id},
        sequence=sequence,
    )


def test_session_secret_is_not_stored_plaintext() -> None:
    session = DeviceSession("device-1")
    secret = session.provision_secret()
    assert session.authenticate(secret) is True
    assert session.state is SessionState.CONNECTED
    assert secret not in repr(session)


def test_revoked_session_cannot_authenticate() -> None:
    session = DeviceSession("device-1")
    secret = session.provision_secret()
    session.revoke()
    assert session.authenticate(secret) is False


def test_router_rejects_replay() -> None:
    router = TransportRouter()
    assert router.receive("c1", message(1))["status"] == "accepted"
    with pytest.raises(ValueError):
        router.receive("c1", message(1))


def test_router_rejects_missing_device_id() -> None:
    router = TransportRouter()
    invalid = BridgeMessage(
        id="m-1", type=MessageType.HEARTBEAT, timestamp_ms=1,
        payload={}, sequence=1,
    )
    with pytest.raises(ValueError):
        router.receive("c1", invalid)
