import pytest

from tom.action_verification import ActionSpecificVerifier
from tom.models import Risk, ToolCall, ToolResult


@pytest.fixture
def verifier() -> ActionSpecificVerifier:
    return ActionSpecificVerifier()


def test_open_app_requires_expected_package(verifier):
    call = ToolCall(name="open_app", risk=Risk.LOW, arguments={"package_name": "com.example.app"})
    result = ToolResult(tool="open_app", success=True, output={"accepted": True})
    ok = verifier.verify(call, result, after={"package": "com.example.app"})
    bad = verifier.verify(call, result, after={"package": "com.other"})
    assert ok.ok and ok.confidence == 1.0
    assert not bad.ok


def test_tap_requires_expected_state(verifier):
    call = ToolCall(name="tap", risk=Risk.LOW, arguments={"expected_text": "Settings"})
    result = ToolResult(tool="tap", success=True, output={"accepted": True})
    ok = verifier.verify(call, result, after={"nodes": [{"text": "Settings"}]})
    bad = verifier.verify(call, result, after={"nodes": [{"text": "Home"}]})
    assert ok.ok
    assert not bad.ok


def test_search_requires_result_state(verifier):
    call = ToolCall(name="device_search_google", risk=Risk.LOW, arguments={"query": "flights Delhi Goa"})
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    ok = verifier.verify(call, result, after={"nodes": [{"text": "Search results"}, {"text": "flights"}, {"text": "Delhi Goa"}]})
    bad = verifier.verify(call, result, after={"nodes": [{"text": "Google"}]})
    assert ok.ok
    assert not bad.ok


def test_set_text_requires_expected_value(verifier):
    call = ToolCall(name="set_text_node", risk=Risk.LOW, arguments={"text": "hello world"})
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    assert verifier.verify(call, result, after={"nodes": [{"text": "hello world"}]}).ok
    assert not verifier.verify(call, result, after={"nodes": [{"text": "hello"}]}).ok


def test_send_requires_positive_provider_or_ui_evidence(verifier):
    call = ToolCall(name="send_message", risk=Risk.HIGH, arguments={"recipient": "x", "message": "hello"})
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    assert verifier.verify(call, result, after={"nodes": [{"text": "Message sent"}]}).ok
    assert not verifier.verify(call, result, after={"nodes": [{"text": "Draft"}]}).ok


def test_calendar_uses_provider_event_id(verifier):
    call = ToolCall(name="create_calendar_event", risk=Risk.HIGH, arguments={"title": "Trip"})
    result = ToolResult(tool=call.name, success=True, output={"id": "evt-123"})
    verdict = verifier.verify(call, result, after={"nodes": [{"text": "Trip"}]}, provider={"id": "evt-123"})
    assert verdict.ok
    assert verdict.predicate == "calendar.event_created"


def test_upi_requires_provider_success_or_visible_success(verifier):
    call = ToolCall(name="device_upi_payment", risk=Risk.CRITICAL, arguments={"pa": "merchant@upi", "pn": "Merchant", "am": "100"})
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    success = verifier.verify(call, result, provider={"status": "SUCCESS", "transaction_id": "UTR123"})
    pending = verifier.verify(call, result, after={"nodes": [{"text": "Payment Pending"}]}, provider={"status": "PENDING"})
    assert success.ok and success.predicate == "upi.provider_success"
    assert not pending.ok


def test_unknown_action_keeps_safe_fallback(verifier):
    call = ToolCall(name="read_only", arguments={}, risk=Risk.READ)
    result = ToolResult(tool="read_only", success=True, output={"value": 1})
    verdict = verifier.verify(call, result)
    assert verdict.ok
    assert verdict.predicate == "tool_success"
