from tom.action_safety import ActionPreconditionChecker
from tom.agent_state import StepState, TaskState
from tom.models import Risk, ToolCall


def test_task_progress_and_bounded_recovery():
    task = TaskState("c1", "demo", [StepState(0, "device_open_url")])
    task.start_current()
    task.finish(False, error="stale screen")
    assert task.recover_or_advance() == "retry"
    task.start_current()
    task.finish(True)
    assert task.recover_or_advance() == "complete"
    assert task.completed
    assert task.progress() == 1.0


def test_precondition_rejects_stale_screen():
    checker = ActionPreconditionChecker()
    call = ToolCall(
        name="device_open_url",
        risk=Risk.READ,
        arguments={"url": "https://example.com", "expected_fingerprint": "old"},
    )
    result = checker.check(call, observed_state={"fingerprint": "new"})
    assert not result.ok
    assert "stale" in result.reason


def test_precondition_rejects_missing_consequential_argument():
    checker = ActionPreconditionChecker()
    call = ToolCall(name="device_send_message", risk=Risk.HIGH, arguments={"recipient": "x"})
    result = checker.check(call)
    assert not result.ok
    assert "message" in result.reason


def test_upi_accepts_structured_payload_or_intent_uri():
    checker = ActionPreconditionChecker()
    structured = ToolCall(
        name="device_upi_payment",
        risk=Risk.CRITICAL,
        arguments={"pa": "merchant@upi", "pn": "Merchant", "am": "100", "approved": True},
    )
    intent = ToolCall(
        name="device_upi_payment",
        risk=Risk.CRITICAL,
        arguments={"intent_uri": "upi://pay?pa=merchant@upi&am=100", "approved": True},
    )
    assert checker.check(structured).ok
    assert checker.check(intent).ok


def test_calendar_accepts_millis_payload():
    checker = ActionPreconditionChecker()
    call = ToolCall(
        name="device_create_calendar_event",
        risk=Risk.HIGH,
        arguments={"title": "Meeting", "start_millis": 1000, "end_millis": 2000, "approved": True},
    )
    assert checker.check(call).ok
