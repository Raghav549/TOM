import pytest

from tom.action_verification import ActionSpecificVerifier
from tom.models import Risk, ToolCall, ToolResult


@pytest.mark.parametrize(
    ("call", "after", "expected"),
    [
        (ToolCall(name="open_app", risk=Risk.LOW, arguments={"package_name": "com.x"}), {"package": "com.x"}, True),
        (ToolCall(name="open_app", risk=Risk.LOW, arguments={"package_name": "com.x"}), {"package": "com.y"}, False),
        (ToolCall(name="tap", risk=Risk.LOW, arguments={"expected_text": "Settings"}), {"nodes": [{"text": "Settings"}]}, True),
        (ToolCall(name="tap", risk=Risk.LOW, arguments={"expected_text": "Settings"}), {"nodes": [{"text": "Home"}]}, False),
    ],
)
def test_action_specific_predicates(call, after, expected):
    verifier = ActionSpecificVerifier()
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    assert verifier.verify(call, result, after=after).ok is expected


def test_upi_never_accepts_transport_success_alone():
    verifier = ActionSpecificVerifier()
    call = ToolCall(
        name="device_upi_payment",
        risk=Risk.CRITICAL,
        arguments={"pa": "merchant@upi", "pn": "Merchant", "am": "100"},
    )
    result = ToolResult(tool=call.name, success=True, output={"accepted": True})
    verdict = verifier.verify(call, result, provider={"status": "PENDING"}, after={"nodes": [{"text": "Waiting for bank"}]})
    assert not verdict.ok
    assert verdict.predicate == "upi.pending"
