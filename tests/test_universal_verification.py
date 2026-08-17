from tom.models import Risk, ToolCall, ToolResult
from tom.universal_verification import RecoveryAction, UniversalActionVerifier


def call(name: str, **arguments: object) -> ToolCall:
    return ToolCall(name=name, arguments=arguments, risk=Risk.LOW)


def test_send_requires_postcondition_evidence() -> None:
    verifier = UniversalActionVerifier()
    result = verifier.verify(
        call("send_message"),
        ToolResult(tool="send_message", success=True, output={"accepted": True}),
        after={"visible_text": ["Chat with Muskan"]},
    )
    assert result.recovery in {RecoveryAction.REGROUND, RecoveryAction.ALTERNATE_ROUTE, RecoveryAction.ASK_USER}


def test_call_connected_is_verified_from_call_state() -> None:
    verifier = UniversalActionVerifier()
    result = verifier.verify(
        call("device_call"),
        ToolResult(tool="device_call", success=True, output={"accepted": True}),
        after={"call_state": "connected"},
    )
    assert result.recovery is RecoveryAction.VERIFIED


def test_payment_needs_authoritative_terminal_provider_evidence() -> None:
    verifier = UniversalActionVerifier()
    pending = verifier.verify(
        call("device_upi_payment"),
        ToolResult(tool="device_upi_payment", success=True, output={"accepted": True}),
        after={"provider_status": "processing"},
    )
    assert pending.recovery is not RecoveryAction.VERIFIED


def test_provider_evidence_is_fused_without_replacing_observation() -> None:
    merged = UniversalActionVerifier.merge_provider_evidence(
        {"foreground_package": "com.example"},
        {"status": "success", "transaction_id": "tx-1", "amount": "100"},
    )
    assert merged["foreground_package"] == "com.example"
    assert merged["provider_status"] == "success"
    assert merged["transaction_id"] == "tx-1"
    assert len(merged["evidence"]) == 3
