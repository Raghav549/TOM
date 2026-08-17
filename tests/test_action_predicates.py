import pytest

from tom.action_predicates import VerificationContext, default_predicates


def evaluate(action, arguments, before, after, tool_result=None):
    return default_predicates().evaluate(VerificationContext(action, arguments, before, after, tool_result))


def test_open_app_requires_expected_package() -> None:
    result = evaluate("open_app", {"package_name": "com.whatsapp"}, {}, {"package": "com.whatsapp"})
    assert result.success is True
    assert result.confidence == 1.0


def test_open_app_rejects_wrong_package() -> None:
    result = evaluate("open_app", {"package_name": "com.whatsapp"}, {}, {"package": "com.instagram.android"})
    assert result.success is False


def test_tap_requires_expected_state() -> None:
    result = evaluate(
        "tap",
        {"expected_text": "Settings", "expected_package": "com.example"},
        {"package": "com.example"},
        {"package": "com.example", "visible_text": ("Settings",)},
    )
    assert result.success is True


def test_search_requires_result_evidence() -> None:
    success = evaluate("search", {"query": "Goa", "expected_result_state": "results"}, {}, {"visible_text": ("Goa flights",), "result_count": 12})
    failure = evaluate("search", {"query": "Goa", "expected_result_state": "results"}, {}, {"visible_text": ("Search",), "result_count": 0})
    assert success.success is True
    assert failure.success is False


def test_message_requires_content_and_delivery() -> None:
    ok = evaluate(
        "send_message",
        {"recipient": "Muskan", "message": "Hi"},
        {},
        {"visible_text": ("Muskan", "Hi", "Delivered")},
    )
    bad = evaluate(
        "send_message",
        {"recipient": "Muskan", "message": "Hi"},
        {},
        {"visible_text": ("Muskan", "Hi")},
    )
    assert ok.success is True
    assert bad.success is False


def test_upi_requires_provider_success_and_transaction_evidence() -> None:
    ok = evaluate(
        "upi_payment",
        {"pa": "merchant@upi", "am": "100"},
        {},
        {"payment_provider": "upi", "payment_status": "success", "transaction_id": "TXN123"},
    )
    failed = evaluate(
        "upi_payment",
        {"pa": "merchant@upi", "am": "100"},
        {},
        {"payment_provider": "upi", "payment_status": "pending"},
    )
    assert ok.success is True
    assert failed.success is False


def test_calendar_requires_saved_state() -> None:
    result = evaluate(
        "create_calendar_event",
        {"title": "Trip"},
        {},
        {"visible_text": ("Trip", "Event saved")},
    )
    assert result.success is True
