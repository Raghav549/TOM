from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
import re

from .models import ToolCall, ToolResult


@dataclass(frozen=True)
class VerificationContext:
    """Evidence collected after a real action.

    Structured Android/browser observations are preferred over textual claims.
    """

    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    provider: Mapping[str, Any] = field(default_factory=dict)
    action_output: Any = None


@dataclass(frozen=True)
class PredicateResult:
    ok: bool
    predicate: str
    confidence: float
    evidence: tuple[str, ...] = ()
    reason: str = ""


class SuccessPredicate(Protocol):
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult: ...


class DefaultSuccessPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        if not result.success:
            return PredicateResult(False, "tool_success", 0.0, (), result.error or "tool failed")
        if result.output is None and not context.after:
            return PredicateResult(False, "observable_success", 0.0, (), "no result or post-action evidence")
        return PredicateResult(True, "tool_success", 0.75, ("tool_result",), "tool returned a successful result")


def _text_values(state: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    nodes = state.get("nodes") or []
    for node in nodes:
        if not isinstance(node, Mapping) or node.get("password"):
            continue
        for key in ("text", "content_description", "class_name", "description"):
            value = str(node.get(key) or "").strip()
            if value:
                values.append(value)
    tree = state.get("tree")
    if isinstance(tree, Mapping):
        stack = [tree]
        while stack:
            node = stack.pop()
            if not isinstance(node, Mapping) or node.get("password"):
                continue
            for key in ("text", "description", "class"):
                value = str(node.get(key) or "").strip()
                if value:
                    values.append(value)
            stack.extend(node.get("children") or [])
    return values


def _normalized_text(state: Mapping[str, Any]) -> str:
    return " ".join(_text_values(state)).lower()


class OpenAppPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        expected = str(call.arguments.get("expected_package") or call.arguments.get("package_name") or "").strip()
        actual = str(context.after.get("package") or context.after.get("package_name") or "").strip()
        if not expected:
            return PredicateResult(False, "open_app.expected_package", 0.0, (), "expected package is required")
        if actual == expected:
            return PredicateResult(True, "open_app.expected_package", 1.0, (f"package={actual}",), "expected package is active")
        return PredicateResult(False, "open_app.expected_package", 0.0, (f"package={actual or 'unknown'}",), f"expected {expected}")


class TapPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        expected_text = str(call.arguments.get("expected_text") or call.arguments.get("expected_target") or "").strip()
        expected_package = str(call.arguments.get("expected_package") or "").strip()
        after_text = _normalized_text(context.after)
        evidence: list[str] = []
        if expected_package:
            actual_package = str(context.after.get("package") or context.after.get("package_name") or "")
            if actual_package != expected_package:
                return PredicateResult(False, "tap.expected_package", 0.0, (f"package={actual_package}",), "expected package mismatch")
            evidence.append(f"package={actual_package}")
        if expected_text:
            target = expected_text.lower()
            if target not in after_text:
                return PredicateResult(False, "tap.expected_ui_target", 0.0, (), f"expected UI target/state not found: {expected_text}")
            evidence.append(f"visible={expected_text}")
        if expected_text or expected_package:
            return PredicateResult(True, "tap.expected_ui_target", 0.96, tuple(evidence), "expected post-tap state observed")
        before_fp = str(context.before.get("fingerprint") or "")
        after_fp = str(context.after.get("fingerprint") or "")
        if before_fp and after_fp and before_fp != after_fp:
            return PredicateResult(True, "tap.state_transition", 0.72, ("screen_fingerprint_changed",), "tap produced a state transition")
        return PredicateResult(False, "tap.observable_transition", 0.25, (), "tap has no action-specific success evidence")


class SearchPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        query = str(call.arguments.get("query") or "").strip()
        expected_package = str(call.arguments.get("expected_package") or "").strip()
        text = _normalized_text(context.after)
        if expected_package:
            actual_package = str(context.after.get("package") or context.after.get("package_name") or "")
            if actual_package != expected_package:
                return PredicateResult(False, "search.expected_package", 0.0, (f"package={actual_package}",), "search result app mismatch")
        result_signals = (
            "results", "search results", "web results", "flights", "news", "shopping", "images", "maps",
            "result for", "found",
        )
        found_signal = any(signal in text for signal in result_signals)
        query_tokens = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2}
        overlap = sum(token in text for token in query_tokens) / max(1, len(query_tokens))
        if found_signal and overlap >= 0.2:
            return PredicateResult(True, "search.expected_result_state", min(0.99, 0.72 + overlap * 0.25), ("result_signal", f"query_overlap={overlap:.2f}"), "search result state observed")
        if found_signal:
            return PredicateResult(True, "search.result_state", 0.70, ("result_signal",), "result-like state observed")
        return PredicateResult(False, "search.expected_result_state", 0.25, (), "expected search result state not observed")


class SetTextPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        expected = str(call.arguments.get("text") or "")
        if not expected:
            return PredicateResult(False, "set_text.expected_value", 0.0, (), "text is required")
        if expected in _normalized_text(context.after):
            return PredicateResult(True, "set_text.expected_value", 0.98, ("text_visible",), "expected value visible after typing")
        return PredicateResult(False, "set_text.expected_value", 0.0, (), "expected value not observed")


class ComposePredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        recipient = str(call.arguments.get("recipient") or "").strip().lower()
        body = str(call.arguments.get("body") or call.arguments.get("text") or "").strip().lower()
        text = _normalized_text(context.after)
        evidence: list[str] = []
        if recipient and recipient not in text:
            return PredicateResult(False, "compose.recipient", 0.0, (), "recipient not visible in composer")
        if recipient:
            evidence.append("recipient_visible")
        if body and body[:80] not in text:
            return PredicateResult(False, "compose.body", 0.0, (), "message body not visible in composer")
        if body:
            evidence.append("body_visible")
        return PredicateResult(True, "compose.composer_ready", 0.94, tuple(evidence), "composer contains requested payload")


class SendPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        text = _normalized_text(context.after)
        sent_signals = ("sent", "message sent", "delivered", "submitted", "success", "email sent")
        if any(signal in text for signal in sent_signals):
            return PredicateResult(True, "send.provider_state", 0.96, ("positive_send_state",), "post-send state observed")
        provider = context.provider
        provider_status = str(provider.get("status") or provider.get("state") or provider.get("transaction_status") or "").lower()
        if provider_status in {"success", "successful", "sent", "delivered", "completed", "submitted"}:
            return PredicateResult(True, "send.provider_state", 0.99, (f"provider_status={provider_status}",), "provider reports successful send")
        return PredicateResult(False, "send.provider_state", 0.20, (), "no positive post-send evidence")


class CalendarPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        expected_title = str(call.arguments.get("title") or "").strip().lower()
        text = _normalized_text(context.after)
        if expected_title and expected_title not in text:
            return PredicateResult(False, "calendar.event_visible", 0.0, (), "calendar event title not observed")
        provider = context.provider
        event_id = str(provider.get("id") or provider.get("event_id") or "")
        if event_id:
            return PredicateResult(True, "calendar.event_created", 0.99, (f"event_id={event_id}",), "calendar provider returned event id")
        if expected_title:
            return PredicateResult(True, "calendar.event_visible", 0.86, ("event_title_visible",), "event visible in calendar")
        return PredicateResult(False, "calendar.event_created", 0.25, (), "calendar creation evidence missing")


class UpiPredicate:
    def evaluate(self, call: ToolCall, result: ToolResult, context: VerificationContext) -> PredicateResult:
        provider = context.provider
        text = _normalized_text(context.after)
        status = str(provider.get("status") or provider.get("state") or provider.get("transaction_status") or "").lower()
        transaction_id = str(provider.get("transaction_id") or provider.get("txn_id") or provider.get("utr") or "")
        positive_provider = status in {"success", "successful", "completed", "paid"}
        positive_ui = any(signal in text for signal in ("payment successful", "payment complete", "transaction successful", "paid successfully"))
        if positive_provider and transaction_id:
            return PredicateResult(True, "upi.provider_success", 1.0, (f"status={status}", "transaction_id_present"), "provider success evidence with transaction identifier")
        if positive_provider:
            return PredicateResult(True, "upi.provider_success", 0.92, (f"status={status}",), "provider reports success")
        if positive_ui:
            return PredicateResult(True, "upi.ui_success", 0.88, ("positive_payment_ui",), "payment success state visible")
        if status in {"pending", "processing"} or "payment pending" in text:
            return PredicateResult(False, "upi.pending", 0.65, ("pending_state",), "payment is pending, not successful")
        return PredicateResult(False, "upi.provider_or_ui_success", 0.0, (), "no trustworthy payment success evidence")


class PredicateRegistry:
    def __init__(self) -> None:
        self._predicates: dict[str, SuccessPredicate] = {}
        self._default = DefaultSuccessPredicate()
        self.register("open_app", OpenAppPredicate())
        self.register("tap", TapPredicate())
        self.register("tap_node", TapPredicate())
        self.register("search_google", SearchPredicate())
        self.register("device_search_google", SearchPredicate())
        self.register("set_text_node", SetTextPredicate())
        self.register("device_type", SetTextPredicate())
        self.register("compose_email", ComposePredicate())
        self.register("compose_sms", ComposePredicate())
        self.register("device_compose_email", ComposePredicate())
        self.register("device_compose_sms", ComposePredicate())
        for name in ("send_message", "send_email", "send_sms", "send_form", "communication.sms_send", "google.gmail_send"):
            self.register(name, SendPredicate())
        self.register("create_calendar_event", CalendarPredicate())
        self.register("device_create_calendar_event", CalendarPredicate())
        self.register("device_upi_payment", UpiPredicate())
        self.register("upi_payment", UpiPredicate())

    def register(self, action: str, predicate: SuccessPredicate) -> None:
        self._predicates[action] = predicate

    def get(self, action: str) -> SuccessPredicate:
        return self._predicates.get(action, self._default)


class ActionSpecificVerifier:
    """Verifies semantic success, not transport success or generic screen change."""

    def __init__(self, predicates: PredicateRegistry | None = None) -> None:
        self.predicates = predicates or PredicateRegistry()

    def verify(
        self,
        call: ToolCall,
        result: ToolResult,
        *,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        provider: Mapping[str, Any] | None = None,
    ) -> PredicateResult:
        context = VerificationContext(before=before or {}, after=after or {}, provider=provider or {}, action_output=result.output)
        return self.predicates.get(call.name).evaluate(call, result, context)
