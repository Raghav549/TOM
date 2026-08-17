from __future__ import annotations

from typing import Any, Mapping

from .success_predicates import SuccessPredicateEngine, VerificationResult, VerificationState


_TERMINAL_FAILURES = {
    "failed", "failure", "error", "declined", "rejected", "cancelled", "canceled",
    "denied", "blocked", "expired", "reversed", "disconnected", "busy",
}
_PENDING = {"pending", "processing", "queued", "initiated", "connecting", "ringing", "loading", "submitted"}
_SUCCESS = {"success", "successful", "succeeded", "completed", "complete", "sent", "delivered", "connected", "joined", "published", "booked", "uploaded", "downloaded", "saved"}


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _blob(obs: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in ("visible_text", "content_descriptions", "notification_text", "page_text", "result_text"):
        value = obs.get(key, ())
        if isinstance(value, (list, tuple)):
            values.extend(str(x) for x in value)
        elif value:
            values.append(str(value))
    return " ".join(values).casefold()


def _state(obs: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = obs.get(key)
        if value is not None and str(value).strip():
            return _norm(value)
    return ""


def _evidence(obs: Mapping[str, Any]) -> tuple[Any, ...]:
    raw = obs.get("evidence", ())
    return tuple(raw) if isinstance(raw, (list, tuple)) else ()


def _terminal_evidence(obs: Mapping[str, Any], values: set[str]) -> bool:
    for item in _evidence(obs):
        if isinstance(item, Mapping):
            value = _norm(item.get("value"))
            if item.get("authoritative") is True and float(item.get("confidence", 0.0) or 0.0) >= 0.90 and value in values:
                return True
    return False


class StrictSuccessPredicateEngine(SuccessPredicateEngine):
    """Production gate: ACK/screen-change is never sufficient for consequential actions."""

    def verify(self, action: Mapping[str, Any], observation: Mapping[str, Any] | None) -> VerificationResult:
        result = super().verify(action, observation)
        obs = observation or {}
        kind = _norm(action.get("kind", action.get("tool", "generic")))
        expected = action.get("success_predicate", action.get("expected", {})) or {}
        if not isinstance(expected, Mapping):
            expected = {}

        # A failed or pending provider/device state always dominates a visual positive.
        state = _state(obs, "provider_status", "payment_state", "transaction_status", "call_state", "video_call_state", "send_state", "form_state", "file_state")
        if state in _TERMINAL_FAILURES:
            return VerificationResult(VerificationState.FAILED, f"authoritative state is {state}", 1.0, result.evidence, obs)
        if kind in {"payment", "upi", "send", "call", "video_call", "book", "form_submit", "upload", "download", "publish", "delete"} and state in _PENDING:
            return VerificationResult(VerificationState.UNKNOWN, f"action remains in non-terminal state: {state}", max(result.confidence, 0.95), result.evidence, obs)

        if kind == "tap" or kind == "tap_node":
            if not any(expected.get(key) for key in ("target", "expected_text", "expected_package", "post_state", "state", "expected_screen", "expected_fingerprint")):
                return VerificationResult(VerificationState.UNKNOWN, "tap has no action-specific success predicate", 0.0, result.evidence, obs)
            if expected.get("expected_fingerprint") and _norm(obs.get("fingerprint")) != _norm(expected["expected_fingerprint"]):
                return VerificationResult(VerificationState.FAILED, "tap expected fingerprint not observed", 1.0, result.evidence, obs)

        if kind == "search":
            result_count = obs.get("result_count", obs.get("results_count"))
            results = obs.get("results")
            has_results = isinstance(results, (list, tuple)) and len(results) > 0
            if expected.get("require_results", True) and not has_results and not (isinstance(result_count, int) and result_count > 0):
                if _state(obs, "result_state", "search_state") in {"no_results", "empty"}:
                    return VerificationResult(VerificationState.FAILED, "search completed with no results", 1.0, result.evidence, obs)
                return VerificationResult(VerificationState.UNKNOWN, "search result existence is not proven", result.confidence, result.evidence, obs)

        if kind in {"send", "compose"}:
            body = _norm(expected.get("body", expected.get("text", "")))
            recipient = _norm(expected.get("recipient", ""))
            blob = _blob(obs)
            if kind == "send":
                payload_ok = (not body or body in blob or _norm(obs.get("message_body", obs.get("sent_body", ""))) == body)
                recipient_ok = (not recipient or recipient in blob or _norm(obs.get("recipient", obs.get("sent_to", ""))) == recipient)
                terminal = _terminal_evidence(obs, {"sent", "delivered", "success", "completed"}) or _state(obs, "send_state", "message_state", "provider_status") in {"sent", "delivered", "success", "completed"}
                if terminal and payload_ok and recipient_ok:
                    return VerificationResult(VerificationState.VERIFIED, "message delivery/send evidence confirmed", max(result.confidence, 0.97), result.evidence, obs)
                return VerificationResult(VerificationState.UNKNOWN, "message send is not proven with terminal delivery evidence", result.confidence, result.evidence, obs)

        if kind in {"call", "video_call"}:
            target = _norm(expected.get("contact", expected.get("recipient", "")))
            actual = _norm(obs.get("connected_contact", obs.get("contact", obs.get("phone_number", ""))))
            connected = _state(obs, "call_state", "telephony_state", "video_call_state") in {"connected", "in_call", "joined", "answered"}
            target_ok = not target or target == actual or target in _blob(obs)
            if connected and target_ok:
                return VerificationResult(VerificationState.VERIFIED, "call/video-call connection and target confirmed", max(result.confidence, 0.97), result.evidence, obs)
            return VerificationResult(VerificationState.UNKNOWN, "call/video-call connection is not proven", result.confidence, result.evidence, obs)

        if kind in {"form_submit", "book", "publish", "delete", "upload", "download"}:
            success_state = _state(obs, "form_state", "booking_state", "publish_state", "delete_state", "file_state", "upload_state", "download_state")
            success_text = _norm(expected.get("success_text", ""))
            if success_state in _SUCCESS or (success_text and success_text in _blob(obs)):
                return VerificationResult(VerificationState.VERIFIED, f"{kind} terminal success evidence confirmed", max(result.confidence, 0.96), result.evidence, obs)
            if obs.get("validation_errors") or success_state in _TERMINAL_FAILURES:
                return VerificationResult(VerificationState.FAILED, f"{kind} failed or validation errors remain", 1.0, result.evidence, obs)
            return VerificationResult(VerificationState.UNKNOWN, f"{kind} terminal success is not proven", result.confidence, result.evidence, obs)

        if kind == "notification":
            notification_id = expected.get("notification_id")
            package = expected.get("package") or expected.get("expected_package")
            notifications = obs.get("notifications", ())
            if isinstance(notifications, (list, tuple)):
                for item in notifications:
                    if not isinstance(item, Mapping):
                        continue
                    if notification_id and str(item.get("id")) == str(notification_id):
                        return VerificationResult(VerificationState.VERIFIED, "expected notification observed", .98, result.evidence, obs)
                    if package and _norm(item.get("package")) == _norm(package):
                        return VerificationResult(VerificationState.VERIFIED, "notification from expected package observed", .96, result.evidence, obs)
            return VerificationResult(VerificationState.UNKNOWN, "expected notification not yet observed", result.confidence, result.evidence, obs)

        return result
