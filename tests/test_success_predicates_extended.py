import pytest

from tom.success_predicates import SuccessPredicateEngine, VerificationState


@pytest.fixture
def engine() -> SuccessPredicateEngine:
    return SuccessPredicateEngine()


def test_send_requires_payload_and_terminal_state(engine: SuccessPredicateEngine) -> None:
    result = engine.verify(
        {"kind": "send", "expected": {"recipient": "Muskan", "body": "Hi"}},
        {"message_state": "sent", "visible_text": ["Message sent", "Muskan", "Hi"]},
    )
    assert result.state is VerificationState.VERIFIED

    incomplete = engine.verify(
        {"kind": "send", "expected": {"recipient": "Muskan", "body": "Hi"}},
        {"message_state": "sent", "visible_text": ["Message sent"]},
    )
    assert incomplete.state is VerificationState.UNKNOWN


def test_payment_pending_never_becomes_success(engine: SuccessPredicateEngine) -> None:
    result = engine.verify(
        {"kind": "upi", "expected": {"provider": "upi"}},
        {"provider_payment_state": "pending", "transaction_id": "T1"},
    )
    assert result.state is VerificationState.UNKNOWN


def test_booking_requires_confirmation_id(engine: SuccessPredicateEngine) -> None:
    result = engine.verify(
        {"kind": "book", "expected": {}},
        {"booking_state": "confirmed", "confirmation_id": "ABC123"},
    )
    assert result.state is VerificationState.VERIFIED

    no_id = engine.verify({"kind": "book", "expected": {}}, {"booking_state": "confirmed"})
    assert no_id.state is VerificationState.UNKNOWN


def test_video_call_requires_media_state(engine: SuccessPredicateEngine) -> None:
    result = engine.verify(
        {"kind": "video_call", "expected": {"contact": "Muskan", "video": True}},
        {"call_state": "connected", "connected_contact": "Muskan", "camera_active": True, "audio_active": True},
    )
    assert result.state is VerificationState.VERIFIED

    missing_video = engine.verify(
        {"kind": "video_call", "expected": {"contact": "Muskan", "video": True}},
        {"call_state": "connected", "connected_contact": "Muskan", "camera_active": False, "audio_active": True},
    )
    assert missing_video.state is VerificationState.UNKNOWN


def test_notification_requires_matching_source_and_content(engine: SuccessPredicateEngine) -> None:
    result = engine.verify(
        {"kind": "notification", "expected": {"package": "com.whatsapp", "text": "hello"}},
        {"notification_package": "com.whatsapp", "notification_text": "Muskan: hello", "notification_id": 7},
    )
    assert result.state is VerificationState.VERIFIED
