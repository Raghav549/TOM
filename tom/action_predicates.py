from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class PredicateEvidence:
    source: str
    detail: str
    weight: float = 1.0


@dataclass(frozen=True)
class PredicateResult:
    success: bool
    confidence: float
    reason: str
    evidence: tuple[PredicateEvidence, ...] = ()


@dataclass(frozen=True)
class VerificationContext:
    action: str
    arguments: Mapping[str, Any]
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None
    tool_result: Mapping[str, Any] | None = None


class SuccessPredicate:
    name: str = "base"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        raise NotImplementedError


@dataclass(frozen=True)
class OpenAppPredicate(SuccessPredicate):
    name: str = "open_app"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        expected = str(context.arguments.get("package_name") or context.arguments.get("expected_package") or "").strip()
        actual = str(after.get("package_name") or after.get("package") or "").strip()
        if not expected:
            return PredicateResult(False, 0.0, "expected package is required for open_app verification")
        ok = actual == expected
        return PredicateResult(ok, 1.0 if ok else 0.0, "expected Android package is foreground" if ok else f"foreground package {actual!r} != {expected!r}", (
            PredicateEvidence("accessibility", f"package={actual}"),
        ))


@dataclass(frozen=True)
class TapPredicate(SuccessPredicate):
    name: str = "tap"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        args = context.arguments
        expected_text = str(args.get("expected_text") or args.get("expected_target") or "").strip().lower()
        expected_package = str(args.get("expected_package") or "").strip()
        visible = _visible_text(after)
        checks: list[PredicateEvidence] = []
        if expected_package:
            actual_package = str(after.get("package_name") or after.get("package") or "")
            checks.append(PredicateEvidence("package", f"package={actual_package}"))
            if actual_package != expected_package:
                return PredicateResult(False, 0.0, "tap reached an unexpected package", tuple(checks))
        if expected_text:
            matched = any(expected_text in text.lower() for text in visible)
            checks.append(PredicateEvidence("ui_text", f"expected={expected_text!r}; matched={matched}"))
            if not matched:
                return PredicateResult(False, 0.1, "expected post-tap UI target/state was not observed", tuple(checks))
        if expected_text or expected_package:
            return PredicateResult(True, 0.95, "post-tap target/state matched", tuple(checks))
        return PredicateResult(False, 0.0, "tap requires an expected UI target, state, package, or fingerprint")


@dataclass(frozen=True)
class SearchPredicate(SuccessPredicate):
    name: str = "search"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        expected = str(context.arguments.get("expected_result") or context.arguments.get("query") or "").strip().lower()
        result_state = str(context.arguments.get("expected_result_state") or "").strip().lower()
        visible = _visible_text(after)
        matched = bool(expected and any(expected in text.lower() for text in visible))
        results_count = _result_count(after)
        evidence = [PredicateEvidence("ui_text", f"query_or_expected={expected!r}; matched={matched}")]
        if results_count is not None:
            evidence.append(PredicateEvidence("ui_structure", f"result_count={results_count}"))
        if result_state == "results" and results_count is not None:
            matched = matched or results_count > 0
        if matched:
            return PredicateResult(True, 0.9, "search result state observed", tuple(evidence))
        return PredicateResult(False, 0.15, "search result state not proven", tuple(evidence))


@dataclass(frozen=True)
class TextEntryPredicate(SuccessPredicate):
    name: str = "set_text"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        expected = str(context.arguments.get("text") or "")
        if not expected:
            return PredicateResult(False, 0.0, "text argument required")
        texts = _visible_text(after)
        matched = any(expected == text or expected in text for text in texts)
        return PredicateResult(matched, 0.95 if matched else 0.0, "entered text observed" if matched else "entered text not observed", (
            PredicateEvidence("ui_text", f"expected_text_observed={matched}"),
        ))


@dataclass(frozen=True)
class NavigationPredicate(SuccessPredicate):
    name: str = "navigation"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        before = context.before or {}
        before_fp = str(before.get("fingerprint") or "")
        after_fp = str(after.get("fingerprint") or "")
        package_changed = (before.get("package") or before.get("package_name")) != (after.get("package") or after.get("package_name"))
        url_changed = before.get("url") != after.get("url") and bool(after.get("url"))
        changed = before_fp != after_fp or package_changed or url_changed
        return PredicateResult(changed, 0.8 if changed else 0.05, "navigation state changed" if changed else "navigation state not proven", (
            PredicateEvidence("screen_state", f"fingerprint_changed={before_fp != after_fp}"),
            PredicateEvidence("app_url", f"package_changed={package_changed};url_changed={url_changed}"),
        ))


@dataclass(frozen=True)
class ProviderPaymentPredicate(SuccessPredicate):
    name: str = "upi_payment"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        tool = context.tool_result or {}
        explicit_status = str(tool.get("payment_status") or after.get("payment_status") or "").lower()
        provider = str(after.get("payment_provider") or after.get("provider") or "").strip()
        transaction = str(after.get("transaction_id") or after.get("upi_txn_id") or "").strip()
        visible = " ".join(_visible_text(after)).lower()
        negative = any(term in visible for term in ("failed", "declined", "cancelled", "canceled", "pending"))
        positive = explicit_status in {"success", "successful", "completed", "paid"} or any(term in visible for term in ("payment successful", "paid successfully", "transaction successful"))
        evidence: list[PredicateEvidence] = [PredicateEvidence("provider", f"provider={provider or 'unknown'}"), PredicateEvidence("payment_status", explicit_status or "unreported")]
        if transaction:
            evidence.append(PredicateEvidence("transaction", "provider transaction id observed", 1.2))
        if negative:
            return PredicateResult(False, 0.0, "payment success contradicted by provider/payment state", tuple(evidence))
        if positive and transaction:
            return PredicateResult(True, 1.0, "provider/payment success and transaction evidence observed", tuple(evidence))
        if positive:
            return PredicateResult(True, 0.85, "provider reports payment success", tuple(evidence))
        return PredicateResult(False, 0.0, "payment success is not proven; provider evidence required", tuple(evidence))


@dataclass(frozen=True)
class MessageSendPredicate(SuccessPredicate):
    name: str = "send_message"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        expected = str(context.arguments.get("message") or context.arguments.get("text") or "").strip().lower()
        recipient = str(context.arguments.get("recipient") or "").strip().lower()
        visible = _visible_text(after)
        message_seen = bool(expected and any(expected in text.lower() for text in visible))
        recipient_seen = bool(recipient and any(recipient in text.lower() for text in visible))
        delivered = _truthy(after.get("delivered")) or any(term in " ".join(visible).lower() for term in ("delivered", "sent", "message sent"))
        evidence = (
            PredicateEvidence("ui_text", f"message_seen={message_seen};recipient_seen={recipient_seen}"),
            PredicateEvidence("delivery", f"delivered={delivered}"),
        )
        ok = message_seen and delivered
        return PredicateResult(ok, 0.95 if ok else 0.1, "message and delivery evidence observed" if ok else "message send not proven", evidence)


@dataclass(frozen=True)
class CalendarCreatePredicate(SuccessPredicate):
    name: str = "create_calendar_event"

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        after = context.after or {}
        title = str(context.arguments.get("title") or context.arguments.get("text") or "").lower()
        visible = _visible_text(after)
        matched = bool(title and any(title in text.lower() for text in visible))
        saved = _truthy(after.get("calendar_saved")) or any(term in " ".join(visible).lower() for term in ("event created", "event saved", "saved to calendar"))
        ok = matched and saved
        return PredicateResult(ok, 0.95 if ok else 0.0, "calendar event creation evidence observed" if ok else "calendar event creation not proven", (
            PredicateEvidence("ui_text", f"title_seen={matched};saved={saved}"),
        ))


@dataclass
class PredicateRegistry:
    _predicates: dict[str, SuccessPredicate] = field(default_factory=dict)

    def register(self, predicate: SuccessPredicate) -> None:
        self._predicates[predicate.name] = predicate

    def get(self, action: str) -> SuccessPredicate | None:
        normalized = action.strip().lower()
        aliases = {
            "open_app": "open_app",
            "tap": "tap",
            "tap_node": "tap",
            "search_google": "search",
            "search": "search",
            "device_search_google": "search",
            "set_text_node": "set_text",
            "device_type": "set_text",
            "open_url": "navigation",
            "open_intent_uri": "navigation",
            "back": "navigation",
            "home": "navigation",
            "recents": "navigation",
            "send_message": "send_message",
            "device_send_message": "send_message",
            "send_email": "send_message",
            "create_calendar_event": "create_calendar_event",
            "device_create_calendar_event": "create_calendar_event",
            "payment": "upi_payment",
            "device_upi_payment": "upi_payment",
            "upi_payment": "upi_payment",
        }
        return self._predicates.get(aliases.get(normalized, normalized))

    def evaluate(self, context: VerificationContext) -> PredicateResult:
        predicate = self.get(context.action)
        if predicate is None:
            return PredicateResult(False, 0.0, f"no success predicate registered for action: {context.action}")
        return predicate.evaluate(context)


def default_predicates() -> PredicateRegistry:
    registry = PredicateRegistry()
    for predicate in (
        OpenAppPredicate(), TapPredicate(), SearchPredicate(), TextEntryPredicate(), NavigationPredicate(),
        ProviderPaymentPredicate(), MessageSendPredicate(), CalendarCreatePredicate(),
    ):
        registry.register(predicate)
    return registry


def _visible_text(observation: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for value in observation.get("visible_text", ()) or ():
        text = str(value).strip()
        if text:
            values.append(text)
    for node in observation.get("nodes", ()) or ():
        if not isinstance(node, Mapping) or node.get("password"):
            continue
        for key in ("text", "content_description"):
            text = str(node.get(key) or "").strip()
            if text and text not in values:
                values.append(text)
    return values


def _result_count(observation: Mapping[str, Any]) -> int | None:
    for key in ("result_count", "results_count", "search_result_count"):
        value = observation.get(key)
        if isinstance(value, int):
            return value
    return None


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1", "yes", "success", "completed", "paid", "delivered"}
