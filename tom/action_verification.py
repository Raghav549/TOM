from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import ToolCall, ToolResult
from .success_predicates import SuccessPredicateEngine, VerificationState


@dataclass(frozen=True)
class VerificationContext:
    before: Mapping[str, Any] = None  # type: ignore[assignment]
    after: Mapping[str, Any] = None  # type: ignore[assignment]
    provider: Mapping[str, Any] = None  # type: ignore[assignment]
    action_output: Any = None


@dataclass(frozen=True)
class PredicateResult:
    ok: bool
    predicate: str
    confidence: float
    evidence: tuple[str, ...] = ()
    reason: str = ""


class ActionSpecificVerifier:
    """Compatibility facade over the single semantic SuccessPredicateEngine."""

    def __init__(self) -> None:
        self._engine = SuccessPredicateEngine()

    @staticmethod
    def _normalize_observation(observation: Mapping[str, Any] | None) -> dict[str, Any]:
        obs = dict(observation or {})
        nodes = obs.get("nodes")
        if isinstance(nodes, list):
            visible: list[str] = []
            descriptions: list[str] = []
            ids: list[str] = []
            for node in nodes:
                if not isinstance(node, Mapping) or node.get("password"):
                    continue
                for key, target in (("text", visible), ("content_description", descriptions), ("resource_id", ids), ("node_id", ids)):
                    if node.get(key):
                        target.append(str(node[key]))
            obs.setdefault("visible_text", visible)
            obs.setdefault("content_descriptions", descriptions)
            obs.setdefault("resource_ids", ids)
        return obs

    @staticmethod
    def _legacy_expected(call: ToolCall) -> tuple[str, dict[str, Any]]:
        args = dict(call.arguments)
        name = call.name
        if name == "open_app":
            return name, {"package": args.get("expected_package", args.get("package_name"))}
        if name in {"tap", "tap_node"}:
            return name, {"target": args.get("expected_text", args.get("expected_target")), "expected_package": args.get("expected_package"), "post_state": args.get("post_state")}
        if name in {"search_google", "device_search_google"}:
            return "search", {"query": args.get("query", ""), "result_state": args.get("result_state", "loaded"), "result_contains": args.get("result_contains", [])}
        if name in {"set_text_node", "device_type"}:
            return "type", {"value": args.get("text", "")}
        if name in {"send_message", "send_email", "send_sms", "send_form", "communication.sms_send", "google.gmail_send"}:
            return "send", {}
        if name in {"create_calendar_event", "device_create_calendar_event"}:
            return "create_calendar_event", {"title": args.get("title", "")}
        if name in {"device_upi_payment", "upi_payment"}:
            return "upi", {}
        return name, {}

    def verify(self, call: ToolCall, result: ToolResult, *, before: Mapping[str, Any] | None = None, after: Mapping[str, Any] | None = None, provider: Mapping[str, Any] | None = None) -> PredicateResult:
        if not result.success:
            return PredicateResult(False, "tool_success", 0.0, (), result.error or "tool failed")
        kind, expected = self._legacy_expected(call)
        normalized_after = self._normalize_observation(after)
        if provider:
            normalized_after.setdefault("evidence", [])
            if isinstance(normalized_after["evidence"], list):
                for key, value in provider.items():
                    if key in {"status", "state", "transaction_status", "transaction_id", "id", "event_id"}:
                        normalized_after["evidence"].append({"kind": "provider", "value": value, "authoritative": key in {"status", "state", "transaction_status"}, "confidence": 0.99})
                if provider.get("status"):
                    normalized_after["provider_status"] = provider["status"]
                    normalized_after["provider_payment_state"] = provider["status"]
                if provider.get("id") or provider.get("event_id"):
                    normalized_after["event_id"] = provider.get("id", provider.get("event_id"))
                if provider.get("transaction_id"):
                    normalized_after["transaction_id"] = provider["transaction_id"]
        if kind == call.name and not expected:
            return PredicateResult(True, "tool_success", 0.75, ("tool_result",), "tool returned a successful result")
        verification = self._engine.verify({"kind": kind, "success_predicate": expected}, normalized_after)
        predicate = {
            "open_app": "open_app.expected_package",
            "tap": "tap.expected_ui_target",
            "tap_node": "tap.expected_ui_target",
            "search": "search.expected_result_state",
            "type": "set_text.expected_value",
            "send": "send.provider_state",
            "create_calendar_event": "calendar.event_created",
            "upi": "upi.provider_success",
        }.get(kind, "tool_success")
        return PredicateResult(verification.verified, predicate, verification.confidence, tuple(e.kind for e in verification.evidence), verification.reason)
