from tom.action_safety import ActionPreconditionChecker
from tom.models import Risk, ToolCall


def call(name: str, arguments: dict, risk: Risk = Risk.READ) -> ToolCall:
    return ToolCall(name=name, arguments=arguments, risk=risk)


def test_device_tap_requires_grounded_success_predicate() -> None:
    result = ActionPreconditionChecker().check(call("device_tap_node", {"node_id": "3"}))
    assert not result.ok
    assert "success_predicate" in result.reason


def test_device_tap_accepts_grounded_predicate() -> None:
    result = ActionPreconditionChecker().check(call("device_tap_node", {
        "node_id": "3",
        "success_predicate": {"post_state": "chat_open", "target": "Muskan"},
    }))
    assert result.ok


def test_open_app_requires_predicate_even_when_package_is_known() -> None:
    result = ActionPreconditionChecker().check(call("device_open_app", {"package_name": "com.whatsapp"}))
    assert not result.ok


def test_stale_screen_is_fail_closed() -> None:
    result = ActionPreconditionChecker().check(call("device_tap_node", {
        "node_id": "3",
        "expected_fingerprint": "new",
        "success_predicate": {"post_state": "chat_open"},
    }), observed_state={"fingerprint": "old"})
    assert not result.ok
    assert "stale" in result.reason


def test_payment_requires_approval_and_predicate() -> None:
    result = ActionPreconditionChecker().check(call("device_upi_payment", {
        "pa": "merchant@upi", "pn": "Merchant", "am": "100",
        "success_predicate": {"provider_status": "SUCCESS"},
    }, risk=Risk.CRITICAL))
    assert not result.ok
    assert "approval" in result.reason
