from tom.models import ToolCall, ToolResult
from tom.action_verification import ActionSpecificVerifier


def call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(name=name, arguments=arguments)


def ok_result(name: str) -> ToolResult:
    return ToolResult(tool=name, success=True, output={})


def test_open_app_requires_expected_package() -> None:
    verifier = ActionSpecificVerifier()
    result = verifier.verify(call("open_app", {"package_name": "com.whatsapp"}), ok_result("open_app"), after={"package_name": "com.instagram.android"})
    assert result.ok is False


def test_tap_requires_expected_postcondition() -> None:
    verifier = ActionSpecificVerifier()
    result = verifier.verify(call("tap", {"expected_text": "Send", "post_state": "sent"}), ok_result("tap"), after={"visible_text": ["Send"]})
    assert result.ok is False


def test_search_requires_result_evidence() -> None:
    verifier = ActionSpecificVerifier()
    result = verifier.verify(call("search_google", {"query": "Patna weather", "result_state": "loaded"}), ok_result("search_google"), after={"search_query": "Patna weather", "result_state": "loaded", "results": []})
    assert result.ok is False


def test_message_requires_terminal_delivery_evidence() -> None:
    verifier = ActionSpecificVerifier()
    pending = verifier.verify(call("send_message", {"recipient": "Muskan", "message": "Hi"}), ok_result("send_message"), after={"visible_text": ["Hi"], "send_state": "pending"})
    assert pending.ok is False
    success = verifier.verify(call("send_message", {"recipient": "Muskan", "message": "Hi"}), ok_result("send_message"), after={"visible_text": ["Muskan", "Hi", "Delivered"], "send_state": "delivered"})
    assert success.ok is True


def test_video_call_requires_connected_state() -> None:
    verifier = ActionSpecificVerifier()
    ringing = verifier.verify(call("video_call", {"contact": "Muskan"}), ok_result("video_call"), after={"video_call_state": "ringing", "contact": "Muskan"})
    assert ringing.ok is False
    connected = verifier.verify(
        call("video_call", {"contact": "Muskan"}),
        ok_result("video_call"),
        after={
            "video_call_state": "connected",
            "connected_contact": "Muskan",
            "video_active": True,
            "audio_active": True,
        },
    )
    assert connected.ok is True


def test_upi_pending_is_never_success() -> None:
    verifier = ActionSpecificVerifier()
    result = verifier.verify(call("upi_payment", {"amount": "100", "recipient": "merchant@upi"}), ok_result("upi_payment"), after={"payment_state": "pending", "transaction_id": "TXN1"})
    assert result.ok is False


def test_upi_success_requires_terminal_evidence() -> None:
    verifier = ActionSpecificVerifier()
    result = verifier.verify(
        call("upi_payment", {"amount": "100", "recipient": "merchant@upi", "provider": "com.google.android.apps.nbu.paisa.user"}),
        ok_result("upi_payment"),
        after={
            "payment_state": "success",
            "transaction_id": "TXN1",
            "payment_provider": "com.google.android.apps.nbu.paisa.user",
            "payment_amount": "100",
            "payment_recipient": "merchant@upi",
            "evidence": [{"kind": "provider", "value": "success", "authoritative": True, "confidence": 0.99}],
        },
    )
    assert result.ok is True
