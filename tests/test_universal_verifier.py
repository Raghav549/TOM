from tom.universal_verifier import verify_universal


def test_message_requires_recipient_body_and_sent_state() -> None:
    assert verify_universal("send_message", {"recipient": "Muskan", "body": "Hi"}, {"message_state": "sent"})[0] is False
    result = verify_universal("send_message", {"recipient": "Muskan", "body": "Hi"}, {"recipient": "Muskan", "message_body": "Hi", "message_state": "sent"})
    assert result is not None and result[0] is True


def test_call_requires_active_telephony_state() -> None:
    assert verify_universal("call", {}, {"call_state": "ringing"})[0] is False
    assert verify_universal("call", {}, {"call_state": "connected"})[0] is True


def test_video_call_requires_audio_and_video() -> None:
    assert verify_universal("video_call", {}, {"call_state": "connected", "video_active": True})[0] is False
    assert verify_universal("video_call", {}, {"call_state": "connected", "video_active": True, "audio_active": True})[0] is True


def test_payment_requires_provider_success_and_transaction_evidence() -> None:
    result = verify_universal("upi", {"provider": "upi", "amount": 500, "recipient": "shop"}, {"provider": "upi", "amount": 500, "recipient": "shop", "payment_state": "success"})
    assert result is not None and result[0] is False
    result = verify_universal("upi", {"provider": "upi", "amount": 500, "recipient": "shop"}, {"provider": "upi", "amount": 500, "recipient": "shop", "payment_state": "success", "transaction_id": "UTR123"})
    assert result[0] is True


def test_booking_requires_confirmation() -> None:
    assert verify_universal("book", {}, {"booking_state": "booked"})[0] is False
    assert verify_universal("book", {}, {"booking_state": "booked", "confirmation_id": "ABC"})[0] is True
