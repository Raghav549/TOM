import pytest

from tom.action_verification import ActionSpecificVerifier
from tom.models import Risk, ToolCall, ToolResult


def test_verification_gate_rejects_open_app_mismatch():
    verifier = ActionSpecificVerifier()
    call = ToolCall(name="open_app", risk=Risk.LOW, arguments={"package_name": "com.whatsapp"})
    result = ToolResult(tool="open_app", success=True, output={"accepted": True})
    verdict = verifier.verify(call, result, after={"package": "com.instagram"})
    assert verdict.ok is False
    assert verdict.predicate == "open_app.expected_package"


def test_verification_gate_rejects_tap_without_expected_target():
    verifier = ActionSpecificVerifier()
    call = ToolCall(name="tap", risk=Risk.LOW, arguments={"x": 100, "y": 200})
    result = ToolResult(tool="tap", success=True, output={"accepted": True})
    verdict = verifier.verify(call, result, after={"fingerprint": "same"}, before={"fingerprint": "same"})
    assert verdict.ok is False


def test_upi_requires_provider_evidence():
    verifier = ActionSpecificVerifier()
    call = ToolCall(name="device_upi_payment", risk=Risk.CRITICAL, arguments={"pa": "shop@upi", "pn": "Shop", "am": "250"})
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    verdict = verifier.verify(call, result, provider={"status": "PENDING"})
    assert verdict.ok is False
    assert "pending" in verdict.predicate
