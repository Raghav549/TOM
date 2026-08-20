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


@pytest.mark.asyncio
async def test_runtime_passes_model_plan_through_registry_and_verification(tmp_path) -> None:
    from tom.approval import ApprovalGate
    from tom.memory import MemoryStore
    from tom.models import AgentRequest, Risk
    from tom.planner import ModelPlanner, RulePlanner
    from tom.response import Responder
    from tom.tools import ToolRegistry

    class PlannerLLM:
        async def complete(self, messages, **kwargs):
            return '{"goal":"read status","steps":[{"name":"status.read","arguments":{},"risk":"read"}]}'

    class StatusTool:
        name = "status.read"
        description = "Read the current status."
        risk = Risk.READ

        async def run(self, arguments):
            return {"status": "ready", "post_observation": {"status": "ready"}}

    class TestResponder(Responder):
        async def respond(self, **kwargs):
            return "Status is ready."

    registry = ToolRegistry({})
    registry.register(StatusTool())
    runtime = AgentRuntime(
        ModelPlanner(PlannerLLM(), RulePlanner()),
        registry,
        MemoryStore(str(tmp_path)),
        ApprovalGate(required=False),
        responder=TestResponder(),
    )

    response = await runtime.handle(AgentRequest(message="read status"))

    assert response.plan is not None
    assert response.plan.steps[0].name == "status.read"
    assert response.results[0].success is True
    assert response.results[0].output["post_observation"]["status"] == "ready"
    assert runtime.task_state(response.conversation_id)["live"]["last_action_status"] == "succeeded"
