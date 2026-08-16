import pytest

from tom.success_predicates import SuccessPredicateEngine, VerificationState
from tom.verification_policy import VerificationPolicy, VerificationMode


@pytest.fixture
def engine() -> SuccessPredicateEngine:
    return SuccessPredicateEngine()


def verify(engine: SuccessPredicateEngine, kind: str, expected: dict, obs: dict):
    return engine.verify({"kind": kind, "success_predicate": expected}, obs)


def test_open_app_requires_expected_package(engine):
    result = verify(engine, "open_app", {"package": "com.whatsapp"}, {"package": "com.whatsapp"})
    assert result.state is VerificationState.VERIFIED


def test_tap_requires_semantic_postcondition_not_only_screen_change(engine):
    result = verify(engine, "tap", {"target": "Send", "post_state": "chat"}, {"screen_changed": True, "screen": "settings"})
    assert result.state is VerificationState.FAILED
    result = verify(engine, "tap", {"target": "Send", "post_state": "chat"}, {"visible_text": ["Send"], "screen": "chat"})
    assert result.state is VerificationState.VERIFIED


def test_search_requires_result_state_and_relevance(engine):
    result = verify(engine, "search", {"query": "Goa", "result_state": "loaded", "result_contains": ["Goa"]}, {"search_query": "Goa", "result_state": "loaded", "result_text": ["Goa flights"]})
    assert result.state is VerificationState.VERIFIED


def test_type_and_form_submit(engine):
    assert verify(engine, "type", {"value": "hello"}, {"input_value": "hello"}).verified
    assert verify(engine, "form_submit", {"success_text": "Submitted"}, {"form_state": "submitted"}).verified


def test_send_requires_positive_state(engine):
    assert verify(engine, "send", {}, {"send_state": "pending"}).state is VerificationState.UNKNOWN
    assert verify(engine, "send", {}, {"send_state": "sent"}).verified


def test_call_and_video_call(engine):
    assert verify(engine, "call", {}, {"call_state": "connected"}).verified
    assert verify(engine, "video_call", {"video": True}, {"video_call_state": "connected", "video_active": True}).verified


def test_file_operations(engine):
    assert verify(engine, "upload", {"filename": "photo.jpg"}, {"file_state": "uploaded", "filename": "photo.jpg"}).verified
    assert verify(engine, "download", {}, {"download_state": "failed"}).state is VerificationState.FAILED


def test_calendar_and_notification(engine):
    assert verify(engine, "create_calendar_event", {"title": "Trip"}, {"event_id": "evt_1"}).verified
    result = verify(engine, "notification", {"package": "com.whatsapp", "text": "Muskan"}, {"notification_package": "com.whatsapp", "notification_text": "Muskan sent a message", "notification_id": "n1"})
    assert result.verified


def test_upi_requires_authoritative_or_transaction_evidence(engine):
    ui_only = verify(engine, "upi", {}, {"payment_state": "success", "visible_text": ["Payment successful"]})
    assert ui_only.state is VerificationState.UNKNOWN
    provider = verify(engine, "upi", {}, {"payment_state": "success", "transaction_id": "UTR123", "evidence": [{"kind": "provider", "value": "success", "authoritative": True, "confidence": 0.99}]})
    assert provider.verified


def test_unknown_actions_do_not_crash(engine):
    result = engine.verify({"kind": "future_action", "success_predicate": {"ready": True}}, {"ready": True})
    assert result.verified


def test_consequential_policy_is_strict():
    policy = VerificationPolicy()
    requirements = policy.requirements("upi", "consequent")
    assert requirements.mode is VerificationMode.AUTHORITATIVE
    assert requirements.require_authoritative is True
    assert requirements.require_terminal_state is True
