
from tom.approval import ApprovalGate
from tom.models import Risk, ToolCall
from tom.permissions import Decision, PermissionPolicy
from tom.security import redact, safe_log_payload


def test_approval_token_is_stable_and_one_time() -> None:
    gate = ApprovalGate()
    call = ToolCall(name="communications.send", arguments={"text": "hello"}, risk=Risk.HIGH)
    first = gate.approve(call)
    assert first == gate.token_for(call)
    assert gate.consume(call) is True
    assert gate.consume(call) is False


def test_high_impact_requires_approval() -> None:
    policy = PermissionPolicy()
    call = ToolCall(name="commerce.purchase", risk=Risk.CRITICAL)
    assert policy.decide(call) is Decision.ASK
    assert policy.decide(call, approved=True) is Decision.ALLOW


def test_secrets_are_redacted() -> None:
    result = redact("Authorization: Bearer abcdefghijklmnopqrstuvwxyz").value
    assert "abcdefghijklmnopqrstuvwxyz" not in result
    assert safe_log_payload({"api_key": "secret"})["api_key"] == "[REDACTED]"
