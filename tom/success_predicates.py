from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class VerificationState(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ActionKind(str, Enum):
    OPEN_APP = "open_app"
    OPEN_URL = "open_url"
    TAP = "tap"
    TAP_NODE = "tap_node"
    LONG_PRESS = "long_press"
    TYPE = "type"
    SEARCH = "search"
    SCROLL = "scroll"
    SWIPE = "swipe"
    BACK = "back"
    HOME = "home"
    RECENTS = "recents"
    SELECT = "select"
    FORM_SUBMIT = "form_submit"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    COMPOSE = "compose"
    SEND = "send"
    CALL = "call"
    VIDEO_CALL = "video_call"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    PAYMENT = "payment"
    UPI = "upi"
    NOTIFICATION = "notification"
    GENERIC = "generic"


@dataclass(frozen=True)
class Evidence:
    kind: str
    value: Any
    confidence: float = 1.0
    authoritative: bool = False
    source: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    state: VerificationState
    reason: str
    confidence: float
    evidence: tuple[Evidence, ...] = ()
    observed: Mapping[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.state is VerificationState.VERIFIED


class PredicateError(ValueError):
    pass


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _tokens(value: Any) -> set[str]:
    return {x for x in _norm(value).replace("/", " ").replace("-", " ").split() if len(x) > 1}


def _contains(items: Sequence[Any] | None, expected: Any) -> bool:
    wanted = _norm(expected)
    return bool(items) and any(_norm(item) == wanted for item in items)


def _contains_text(items: Sequence[Any] | None, expected: str) -> bool:
    wanted = _norm(expected)
    return bool(items) and any(wanted in _norm(item) for item in items)


def _text_blob(obs: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in ("visible_text", "content_descriptions", "result_text", "notification_text"):
        raw = obs.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            values.extend(str(x) for x in raw)
        elif raw:
            values.append(str(raw))
    return " ".join(values).casefold()


def _evidence(observation: Mapping[str, Any]) -> tuple[Evidence, ...]:
    raw = observation.get("evidence")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    result: list[Evidence] = []
    for item in raw:
        if isinstance(item, Evidence):
            result.append(item)
        elif isinstance(item, Mapping):
            try:
                confidence = float(item.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 0.0
            result.append(Evidence(str(item.get("kind", "unknown")), item.get("value"), confidence, bool(item.get("authoritative", False)), item.get("source")))
    return tuple(result)


def _fail(reason: str, obs: Mapping[str, Any], evidence: tuple[Evidence, ...] = ()) -> VerificationResult:
    return VerificationResult(VerificationState.FAILED, reason, 0.0, evidence, obs)


def _unknown(reason: str, obs: Mapping[str, Any], evidence: tuple[Evidence, ...] = ()) -> VerificationResult:
    return VerificationResult(VerificationState.UNKNOWN, reason, max((e.confidence for e in evidence), default=0.0), evidence, obs)


def _pass(reason: str, confidence: float, obs: Mapping[str, Any], evidence: tuple[Evidence, ...]) -> VerificationResult:
    return VerificationResult(VerificationState.VERIFIED, reason, max(0.0, min(1.0, confidence)), evidence, obs)


def _package(obs: Mapping[str, Any]) -> str:
    return str(obs.get("foreground_package", obs.get("package", obs.get("package_name", ""))))


class SuccessPredicateEngine:
    """Semantic action verifier: transport ACK/screen-change is never success by itself."""

    DEFAULT_TIMEOUT_MS = 5000
    DEFAULT_POLL_INTERVAL_MS = 250
    DEFAULT_STABILITY_WINDOW_MS = 400

    def verify(self, action: Mapping[str, Any], observation: Mapping[str, Any] | None) -> VerificationResult:
        if observation is None:
            return _unknown("no post-action observation", {})
        raw_kind = str(action.get("kind", action.get("tool", "generic"))).lower().strip()
        try:
            kind = ActionKind(raw_kind)
        except ValueError:
            kind = ActionKind.GENERIC
        expected = action.get("success_predicate", action.get("expected", {}))
        if expected is None:
            return _unknown("action has no success predicate", observation, _evidence(observation))
        if not isinstance(expected, Mapping):
            raise PredicateError("success_predicate must be an object")
        dispatch = {
            ActionKind.OPEN_APP: self._open_app,
            ActionKind.OPEN_URL: self._open_url,
            ActionKind.TAP: self._tap,
            ActionKind.TAP_NODE: self._tap,
            ActionKind.LONG_PRESS: self._tap,
            ActionKind.TYPE: self._type,
            ActionKind.SEARCH: self._search,
            ActionKind.SCROLL: self._movement,
            ActionKind.SWIPE: self._movement,
            ActionKind.BACK: self._navigation,
            ActionKind.HOME: self._navigation,
            ActionKind.RECENTS: self._navigation,
            ActionKind.SELECT: self._tap,
            ActionKind.FORM_SUBMIT: self._submit,
            ActionKind.UPLOAD: self._file_action,
            ActionKind.DOWNLOAD: self._file_action,
            ActionKind.COMPOSE: self._compose,
            ActionKind.SEND: self._send,
            ActionKind.CALL: self._call,
            ActionKind.VIDEO_CALL: self._call,
            ActionKind.CREATE_CALENDAR_EVENT: self._calendar,
            ActionKind.PAYMENT: self._payment,
            ActionKind.UPI: self._payment,
            ActionKind.NOTIFICATION: self._notification,
            ActionKind.GENERIC: self._generic,
        }
        return dispatch[kind](expected, observation)

    def _open_app(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        wanted = expected.get("foreground_package", expected.get("package"))
        if not wanted:
            return _unknown("open_app requires expected package", obs, evidence)
        if _norm(_package(obs)) != _norm(wanted):
            return _fail(f"expected foreground package {wanted!r}, observed {_package(obs)!r}", obs, evidence)
        activity = expected.get("activity")
        if activity and _norm(obs.get("foreground_activity", obs.get("activity"))) != _norm(activity):
            return _fail("expected foreground activity was not observed", obs, evidence)
        anchor = expected.get("ui_anchor")
        if anchor and not (_contains(obs.get("visible_text"), anchor) or _contains(obs.get("content_descriptions"), anchor) or _contains(obs.get("resource_ids"), anchor)):
            return _unknown(f"package is correct but UI anchor {anchor!r} is not confirmed", obs, evidence)
        return _pass("expected app is foreground", 0.99 if not anchor else 0.96, obs, evidence)

    def _open_url(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        url = str(obs.get("url", ""))
        host = str(expected.get("host", "")).strip()
        if host and host.casefold() not in url.casefold():
            return _fail(f"expected URL host {host!r}", obs, evidence)
        if expected.get("url") and _norm(expected["url"]) not in _norm(url):
            return _fail("expected URL was not observed", obs, evidence)
        state = _norm(obs.get("page_state", obs.get("load_state", "")))
        if expected.get("loaded", True) and state not in {"loaded", "interactive", "complete", ""}:
            return _unknown("URL is present but page is not ready", obs, evidence)
        return _pass("expected URL/page confirmed", 0.94, obs, evidence)

    def _tap(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        blob = _text_blob(obs)
        for failure in expected.get("failure_conditions", []) if isinstance(expected.get("failure_conditions", []), Sequence) else []:
            if _norm(failure) in blob:
                return _fail(f"failure condition observed: {failure}", obs, evidence)
        target = expected.get("target", expected.get("expected_text"))
        target_present = bool(target and (_contains(obs.get("visible_text"), target) or _contains(obs.get("content_descriptions"), target) or _contains(obs.get("resource_ids"), target) or _contains(obs.get("node_ids"), target)))
        state = expected.get("post_state", expected.get("state"))
        state_match = bool(state and (_norm(obs.get("screen")) == _norm(state) or _norm(obs.get("ui_state")) == _norm(state) or _norm(obs.get("result_state")) == _norm(state)))
        expected_package = expected.get("expected_package")
        package_match = bool(expected_package and _norm(_package(obs)) == _norm(expected_package))
        if target_present and (not expected_package or package_match) and (not state or state_match):
            return _pass("tap target and expected state confirmed", 0.98, obs, evidence)
        if state_match or (target_present and package_match):
            return _pass("tap postcondition confirmed", 0.90, obs, evidence)
        if expected.get("allow_screen_change_only") and obs.get("screen_changed") is True:
            return _pass("explicit screen-change predicate confirmed", 0.55, obs, evidence)
        return _fail("tap ran but expected target/state was not confirmed", obs, evidence)

    def _type(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        wanted = str(expected.get("value", expected.get("text", "")))
        actual = str(obs.get("input_value", obs.get("focused_input_value", "")))
        if actual == wanted:
            return _pass("typed value confirmed", 0.98, obs, evidence)
        if wanted and wanted.casefold() in _text_blob(obs):
            return _pass("typed value visible in observed UI", 0.86, obs, evidence)
        return _fail("expected typed value is not present", obs, evidence)

    def _search(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        query = str(expected.get("query", "")).strip()
        actual_query = str(obs.get("search_query", obs.get("input_value", ""))).strip()
        if query and _norm(query) != _norm(actual_query):
            return _fail(f"expected query {query!r}, observed {actual_query!r}", obs, evidence)
        state = _norm(obs.get("result_state", obs.get("search_state", "")))
        if state in {"error", "network_error", "blocked", "no_permission"}:
            return _fail(f"search ended in {state}", obs, evidence)
        wanted_state = _norm(expected.get("result_state", "loaded"))
        if state != wanted_state:
            return _unknown("query is set but result state is not confirmed", obs, evidence)
        terms = expected.get("result_contains", [])
        if terms:
            if isinstance(terms, str):
                terms = [terms]
            if not all(_norm(term) in _text_blob(obs) for term in terms):
                return _fail("expected result anchors are missing", obs, evidence)
        return _pass("search query and result state confirmed", 0.94, obs, evidence)

    def _movement(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        if expected.get("expected_scroll_position") is not None and obs.get("scroll_position") == expected["expected_scroll_position"]:
            return _pass("expected scroll position confirmed", 0.92, obs, evidence)
        if expected.get("expected_anchor") and _norm(expected["expected_anchor"]) in _text_blob(obs):
            return _pass("expected post-scroll anchor confirmed", 0.90, obs, evidence)
        before = expected.get("before_fingerprint")
        after = obs.get("fingerprint")
        if before and after and before != after:
            return _pass("movement produced expected state transition", 0.78, obs, evidence)
        return _unknown("movement completed but no grounded postcondition was supplied", obs, evidence)

    def _navigation(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        target_package = expected.get("expected_package")
        if target_package and _norm(_package(obs)) != _norm(target_package):
            return _fail("navigation target package mismatch", obs, evidence)
        target_screen = expected.get("expected_screen", expected.get("post_state"))
        if target_screen and _norm(obs.get("screen", obs.get("ui_state"))) != _norm(target_screen):
            return _fail("navigation target screen mismatch", obs, evidence)
        if target_package or target_screen:
            return _pass("navigation postcondition confirmed", 0.94, obs, evidence)
        if obs.get("navigation_event") in {"home", "back", "recents"}:
            return _pass("system navigation event confirmed", 0.86, obs, evidence)
        return _unknown("navigation has no action-specific postcondition", obs, evidence)

    def _submit(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        if _norm(obs.get("form_state")) in {"submitted", "success", "complete"}:
            return _pass("form submission state confirmed", 0.96, obs, evidence)
        if expected.get("success_text") and _norm(expected["success_text"]) in _text_blob(obs):
            return _pass("form success message confirmed", 0.94, obs, evidence)
        if obs.get("validation_errors"):
            return _fail("form still contains validation errors", obs, evidence)
        return _unknown("form submission has no positive success evidence", obs, evidence)

    def _file_action(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        state = _norm(obs.get("file_state", obs.get("upload_state", obs.get("download_state", ""))))
        if state in {"uploaded", "downloaded", "complete", "completed", "success"}:
            expected_name = expected.get("filename")
            actual_name = str(obs.get("filename", obs.get("file_name", "")))
            if expected_name and _norm(expected_name) not in _norm(actual_name):
                return _fail("expected filename not confirmed", obs, evidence)
            return _pass("file operation confirmed", 0.95, obs, evidence)
        if state in {"failed", "error", "cancelled", "canceled"}:
            return _fail(f"file operation ended in {state}", obs, evidence)
        return _unknown("file operation is not yet confirmed", obs, evidence)

    def _compose(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        recipient = str(expected.get("recipient", "")).strip()
        body = str(expected.get("body", expected.get("text", ""))).strip()
        if recipient and recipient.casefold() not in _text_blob(obs):
            return _fail("recipient is not visible in composer", obs, evidence)
        if body and body[:120].casefold() not in _text_blob(obs):
            return _fail("message body is not visible in composer", obs, evidence)
        return _pass("composer contains requested payload", 0.95, obs, evidence)

    def _send(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        provider = _norm(obs.get("provider_status", obs.get("send_state", obs.get("message_state", ""))))
        if provider in {"failed", "error", "rejected", "cancelled", "canceled"}:
            return _fail(f"send provider reports {provider}", obs, evidence)
        authoritative = [e for e in evidence if e.authoritative and e.confidence >= 0.90]
        if any(_norm(e.value) in {"sent", "delivered", "submitted", "success", "completed"} for e in authoritative):
            return _pass("send confirmed by authoritative evidence", 0.995, obs, tuple(authoritative))
        if provider in {"sent", "delivered", "submitted", "success", "completed"}:
            return _pass("send provider state confirmed", 0.96, obs, evidence)
        if any(x in _text_blob(obs) for x in ("message sent", "sent", "delivered", "email sent", "submitted")):
            return _pass("positive send state visible", 0.90, obs, evidence)
        return _unknown("no trustworthy send success evidence", obs, evidence)

    def _call(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        state = _norm(obs.get("call_state", obs.get("telephony_state", obs.get("video_call_state", ""))))
        wanted = {"connected", "active", "in_call", "ongoing"}
        if state in {"failed", "busy", "rejected", "ended", "disconnected", "error"}:
            return _fail(f"call state is {state}", obs, evidence)
        if state in wanted:
            if expected.get("video") is True and not obs.get("camera_active", obs.get("video_active", False)):
                return _unknown("call is connected but video state is not confirmed", obs, evidence)
            return _pass("call connection state confirmed", 0.97, obs, evidence)
        return _unknown("call is not yet confirmed connected", obs, evidence)

    def _calendar(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        provider_id = str(obs.get("event_id", obs.get("provider_event_id", "")))
        title = str(expected.get("title", ""))
        if provider_id:
            return _pass("calendar provider returned event identifier", 0.995, obs, evidence)
        if title and title.casefold() in _text_blob(obs) and _norm(obs.get("calendar_state")) in {"created", "visible", "success"}:
            return _pass("calendar event is visible", 0.92, obs, evidence)
        return _unknown("calendar creation is not confirmed", obs, evidence)

    def _payment(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        state = _norm(obs.get("provider_payment_state", obs.get("payment_state", "")))
        authoritative_success = any(e.authoritative and e.confidence >= 0.90 and _norm(e.value) in {"success", "succeeded", "completed", "paid"} for e in evidence)
        transaction_id = obs.get("transaction_id", obs.get("txn_id", obs.get("utr")))
        if state in {"failed", "cancelled", "canceled", "declined"}:
            return _fail(f"payment provider reports {state}", obs, evidence)
        if state in {"pending", "processing", "requires_action", "authorization_required"}:
            return _unknown(f"payment remains {state}", obs, evidence)
        if state in {"success", "succeeded", "completed", "paid"} and (authoritative_success or transaction_id):
            return _pass("payment success has provider evidence", 0.999, obs, evidence)
        if any(x in _text_blob(obs) for x in ("payment successful", "payment complete", "transaction successful")):
            return _unknown("payment UI suggests success but provider evidence is missing", obs, evidence)
        return _unknown("no authoritative payment success evidence", obs, evidence)

    def _notification(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        source = str(expected.get("package", expected.get("source", "")))
        text = str(expected.get("text", expected.get("contains", "")))
        notification_package = str(obs.get("notification_package", obs.get("package", "")))
        notification_text = str(obs.get("notification_text", ""))
        if source and _norm(source) != _norm(notification_package):
            return _fail("notification source package mismatch", obs, evidence)
        if text and _norm(text) not in _norm(notification_text):
            return _fail("notification content does not match expected text", obs, evidence)
        if obs.get("notification_id") or notification_text:
            return _pass("notification received and matched", 0.97 if source and text else 0.90, obs, evidence)
        return _unknown("notification has not arrived or has not been observed", obs, evidence)

    def _generic(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        for key, value in expected.items():
            if key in {"timeout_ms", "poll_interval_ms", "stability_window_ms", "failure_conditions"}:
                continue
            if obs.get(key) != value:
                return _fail(f"expected {key}={value!r}, observed {obs.get(key)!r}", obs, evidence)
        return _pass("expected predicate fields observed", 0.90, obs, evidence)
