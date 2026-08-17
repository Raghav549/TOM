from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PredicateResult:
    verified: bool
    confidence: float
    predicate: str
    reason: str
    evidence: tuple[str, ...] = ()


def _str(value: Any) -> str:
    return str(value or "").strip()


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in value.replace("/", " ").replace(".", " ").split() if item}


def _contains_any(values: Sequence[Any], needles: Sequence[str]) -> bool:
    haystack = " ".join(_str(value).lower() for value in values)
    return any(needle.lower() in haystack for needle in needles)


class SuccessPredicateEngine:
    """Verify semantic postconditions, not just that a screen changed."""

    def verify(
        self,
        action: str,
        *,
        expected: Mapping[str, Any] | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        tool_result: Mapping[str, Any] | None = None,
    ) -> PredicateResult:
        expected = expected or {}
        before = before or {}
        after = after or {}
        tool_result = tool_result or {}
        normalized = action.removeprefix("device_").lower()
        dispatch = {
            "open_app": self._open_app,
            "open_url": self._open_url,
            "tap": self._tap,
            "tap_node": self._tap,
            "set_text_node": self._set_text,
            "search_google": self._search,
            "maps_search": self._search,
            "scroll_node_forward": self._scroll,
            "scroll_node_backward": self._scroll,
            "swipe": self._scroll,
            "compose_email": self._compose_email,
            "compose_sms": self._compose_sms,
            "create_calendar_event": self._calendar,
            "open_intent_uri": self._intent,
            "upi_payment": self._upi,
            "send_message": self._message,
            "send_email": self._message,
            "send_sms": self._message,
        }
        predicate = dispatch.get(normalized, self._generic)
        return predicate(expected, before, after, tool_result)

    def _open_app(self, e, b, a, r) -> PredicateResult:
        expected_pkg = _str(e.get("expected_package") or e.get("package_name"))
        actual_pkg = _str(a.get("package_name") or a.get("package"))
        ok = bool(expected_pkg and actual_pkg and expected_pkg == actual_pkg)
        return PredicateResult(ok, 1.0 if ok else 0.0, "package_equals", f"expected={expected_pkg} actual={actual_pkg}", (actual_pkg,))

    def _open_url(self, e, b, a, r) -> PredicateResult:
        expected_url = _str(e.get("expected_url") or e.get("url"))
        actual_url = _str(a.get("url") or a.get("current_url"))
        host_expected = _str(e.get("expected_host"))
        host_actual = actual_url.split("/", 3)[2] if "://" in actual_url else actual_url
        ok = bool((expected_url and actual_url.startswith(expected_url)) or (host_expected and host_actual == host_expected))
        return PredicateResult(ok, 0.98 if ok else 0.0, "url_or_host_matches", f"actual={actual_url}", (host_actual,))

    def _tap(self, e, b, a, r) -> PredicateResult:
        target = _str(e.get("expected_text") or e.get("expected_target") or e.get("expected_node_id"))
        visible = a.get("visible_text") or a.get("texts") or []
        selected = _str(a.get("selected_target") or a.get("focused_target") or a.get("clicked_target"))
        node_ids = a.get("visible_node_ids") or []
        if e.get("expected_node_id"):
            ok = e["expected_node_id"] in node_ids or selected == e["expected_node_id"]
        else:
            ok = bool(target) and (target.lower() in selected.lower() or _contains_any(visible, [target]))
        if not ok and e.get("expected_state")):
            ok = self._state_match(e.get("expected_state", {}), a)
        return PredicateResult(ok, 0.9 if ok else 0.0, "expected_ui_target_or_state", f"target={target}", (selected,))

    def _set_text(self, e, b, a, r) -> PredicateResult:
        expected_text = _str(e.get("expected_text") or e.get("text"))
        actual_text = _str(a.get("field_text") or a.get("text"))
        ok = bool(expected_text and actual_text == expected_text)
        return PredicateResult(ok, 1.0 if ok else 0.0, "field_equals", f"actual={actual_text}", ())

    def _search(self, e, b, a, r) -> PredicateResult:
        query = _str(e.get("query"))
        result_count = int(a.get("result_count") or 0)
        result_state = _str(a.get("result_state") or "").lower()
        visible = a.get("visible_text") or []
        query_seen = not query or query.lower() in " ".join(_str(v).lower() for v in visible)
        ok = (result_count > 0 or result_state in {"results", "search_results"}) and query_seen
        return PredicateResult(ok, 0.92 if ok else 0.0, "search_results_present", f"count={result_count} state={result_state}", (result_state,))

    def _scroll(self, e, b, a, r) -> PredicateResult:
        before_offset = a_number(b, "scroll_offset", 0.0)
        after_offset = a_number(a, "scroll_offset", before_offset)
        direction = _str(e.get("direction") or e.get("expected_direction")).lower()
        moved = after_offset != before_offset
        directional = (direction != "forward" or after_offset > before_offset) and (direction != "backward" or after_offset < before_offset)
        ok = moved and directional
        return PredicateResult(ok, 0.88 if ok else 0.0, "scroll_offset_changed", f"before={before_offset} after={after_offset}", ())

    def _compose_email(self, e, b, a, r) -> PredicateResult:
        recipient = _str(e.get("recipient"))
        composer = _str(a.get("composer") or a.get("package_name"))
        visible = a.get("visible_text") or []
        ok = bool(composer) and (not recipient or _contains_any(visible, [recipient]))
        return PredicateResult(ok, 0.86 if ok else 0.0, "email_composer_open", composer, ())

    def _compose_sms(self, e, b, a, r) -> PredicateResult:
        recipient = _str(e.get("recipient"))
        composer = _str(a.get("composer") or a.get("package_name"))
        visible = a.get("visible_text") or []
        ok = bool(composer) and (not recipient or _contains_any(visible, [recipient]))
        return PredicateResult(ok, 0.86 if ok else 0.0, "sms_composer_open", composer, ())

    def _calendar(self, e, b, a, r) -> PredicateResult:
        title = _str(e.get("title"))
        visible = a.get("visible_text") or []
        event_state = _str(a.get("event_state") or "").lower()
        ok = bool(title) and (title.lower() in " ".join(_str(v).lower() for v in visible) or event_state in {"created", "event_created"})
        return PredicateResult(ok, 0.9 if ok else 0.0, "calendar_event_present", event_state, ())

    def _intent(self, e, b, a, r) -> PredicateResult:
        expected_scheme = _str(e.get("expected_scheme") or "upi")
        actual_scheme = _str(a.get("intent_scheme") or a.get("scheme"))
        provider = _str(a.get("provider") or a.get("payment_app_package"))
        ok = actual_scheme.lower() == expected_scheme.lower() and bool(provider)
        return PredicateResult(ok, 0.93 if ok else 0.0, "intent_provider_open", provider, (actual_scheme, provider))

    def _upi(self, e, b, a, r) -> PredicateResult:
        provider = _str(a.get("payment_provider") or a.get("package_name"))
        payment_state = _str(a.get("payment_state") or "").lower()
        transaction = _str(a.get("transaction_id") or a.get("upi_transaction_id"))
        amount_match = _safe_float(e.get("amount")) is None or _safe_float(e.get("amount")) == _safe_float(a.get("amount"))
        terminal = payment_state in {"success", "completed", "paid"}
        ok = bool(provider and transaction and terminal and amount_match)
        return PredicateResult(ok, 0.99 if ok else 0.0, "provider_terminal_payment_evidence", f"state={payment_state}", (provider, transaction))

    def _message(self, e, b, a, r) -> PredicateResult:
        message_id = _str(a.get("message_id") or a.get("server_message_id") or a.get("delivered_message_id"))
        state = _str(a.get("message_state") or a.get("delivery_state") or "").lower()
        visible = a.get("visible_text") or []
        expected = _str(e.get("message"))
        content_seen = not expected or expected.lower() in " ".join(_str(v).lower() for v in visible)
        ok = bool(message_id) and state in {"sent", "delivered", "accepted"} and content_seen
        return PredicateResult(ok, 0.97 if ok else 0.0, "message_transport_and_content", f"state={state}", (message_id,))

    def _generic(self, e, b, a, r) -> PredicateResult:
        if r.get("verified") is True:
            return PredicateResult(True, 0.8, "tool_verified", "tool adapter reported verified", ())
        changed = _str(b.get("fingerprint")) != _str(a.get("fingerprint"))
        return PredicateResult(changed, 0.65 if changed else 0.0, "state_transition", "state changed" if changed else "state unchanged", ())

    @staticmethod
    def _state_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
        for key, value in expected.items():
            if actual.get(key) != value:
                return False
        return True


def a_number(data: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
