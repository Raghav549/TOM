import pytest

from tom.action_verification import ActionSpecificVerifier
from tom.models import ToolCall, ToolResult
from tom.runtime import AgentRuntime


def _call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(name=name, arguments=arguments, risk="low")


def test_open_app_requires_expected_package() -> None:
    verifier = ActionSpecificVerifier()
    call = _call("open_app", {"package_name": "com.whatsapp"})
    result = ToolResult(tool="open_app", success=True, output={"ack": True})
    verified = verifier.verify(call, result, after={"foreground_package": "com.android.settings"})
    assert verified.ok is False
    assert verified.predicate == "open_app.expected_package"


def test_tap_requires_target_or_explicit_post_state() -> None:
    verifier = ActionSpecificVerifier()
    call = _call("tap", {"target_text": "Send", "post_state": "sent"})
    result = ToolResult(tool="tap", success=True, output={"ack": True})
    verified = verifier.verify(call, result, after={"visible_text": ["Send"], "ui_state": "composer"})
    assert verified.ok is False


def test_fresh_executor_observation_wins_over_stale_context() -> None:
    result = ToolResult(
        tool="open_app",
        success=True,
        output={"ack": True, "post_observation": {"foreground_package": "com.whatsapp"}},
    )
    fresh = AgentRuntime._fresh_observation(result, {"screen_state_after": {"foreground_package": "com.android.settings"}})
    assert fresh["foreground_package"] == "com.whatsapp"


def test_upi_requires_provider_success_evidence() -> None:
    verifier = ActionSpecificVerifier()
    call = _call("upi_payment", {"provider": "upi", "amount": 100, "recipient": "merchant"})
    pending = ToolResult(tool="upi_payment", success=True, output={"status": "pending", "transaction_id": "tx-1"})
    verified = verifier.verify(call, pending, after={"payment_state": "pending"}, provider=pending.output)
    assert verified.ok is False
    assert verified.predicate in {"upi.pending", "upi.provider_evidence"}


@pytest.mark.asyncio
async def test_unknown_postcondition_cannot_become_success() -> None:
    verifier = ActionSpecificVerifier()
    call = _call("search_google", {"query": "open source"})
    result = ToolResult(tool="search_google", success=True, output={"ack": True})
    verified = verifier.verify(call, result, after={"visible_text": ["Loading"]})
    assert verified.ok is False
