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
    TAP = "tap"
    TAP_NODE = "tap_node"
    SEARCH = "search"
    TYPE = "type"
    OPEN_URL = "open_url"
    PAYMENT = "payment"
    UPI = "upi"
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
    return str(value).strip().casefold()


def _contains(items: Sequence[Any] | None, expected: Any) -> bool:
    if not items:
        return False
    wanted = _norm(expected)
    return any(_norm(item) == wanted for item in items)


def _contains_text(items: Sequence[Any] | None, expected: str) -> bool:
    if not items:
        return False
    wanted = _norm(expected)
    return any(wanted in _norm(item) for item in items)


def _evidence(observation: Mapping[str, Any]) -> tuple[Evidence, ...]:
    raw = observation.get("evidence")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    result: list[Evidence] = []
    for item in raw:
        if isinstance(item, Evidence):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(
                Evidence(
                    kind=str(item.get("kind", "unknown")),
                    value=item.get("value"),
                    confidence=float(item.get("confidence", 1.0)),
                    authoritative=bool(item.get("authoritative", False)),
                    source=item.get("source"),
                )
            )
    return tuple(result)


def _fail(reason: str, observation: Mapping[str, Any], evidence: tuple[Evidence, ...] = ()) -> VerificationResult:
    return VerificationResult(VerificationState.FAILED, reason, 0.0, evidence, observation)


def _unknown(reason: str, observation: Mapping[str, Any], evidence: tuple[Evidence, ...] = ()) -> VerificationResult:
    confidence = max((e.confidence for e in evidence), default=0.0)
    return VerificationResult(VerificationState.UNKNOWN, reason, confidence, evidence, observation)


def _pass(reason: str, confidence: float, observation: Mapping[str, Any], evidence: tuple[Evidence, ...]) -> VerificationResult:
    return VerificationResult(VerificationState.VERIFIED, reason, max(0.0, min(1.0, confidence)), evidence, observation)


class SuccessPredicateEngine:
    """Action-aware verifier. Screen transitions alone are never sufficient proof."""

    DEFAULT_TIMEOUT_MS = 5000
    DEFAULT_POLL_INTERVAL_MS = 250
    DEFAULT_STABILITY_WINDOW_MS = 400

    def verify(self, action: Mapping[str, Any], observation: Mapping[str, Any] | None) -> VerificationResult:
        if observation is None:
            return _unknown("no post-action observation")

        kind = ActionKind(str(action.get("kind", action.get("tool", "generic")).lower()).strip())
        expected = action.get("success_predicate", action.get("expected", {}))
        if expected is None:
            return _unknown("action has no success predicate", observation, _evidence(observation))
        if not isinstance(expected, Mapping):
            raise PredicateError("success_predicate must be an object")

        dispatch = {
            ActionKind.OPEN_APP: self._verify_open_app,
            ActionKind.TAP: self._verify_tap,
            ActionKind.TAP_NODE: self._verify_tap,
            ActionKind.SEARCH: self._verify_search,
            ActionKind.TYPE: self._verify_type,
            ActionKind.OPEN_URL: self._verify_open_url,
            ActionKind.PAYMENT: self._verify_payment,
            ActionKind.UPI: self._verify_payment,
            ActionKind.GENERIC: self._verify_generic,
        }
        return dispatch.get(kind, self._verify_generic)(expected, observation)

    def _verify_open_app(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        package = expected.get("foreground_package", expected.get("package"))
        activity = expected.get("activity")
        actual_package = obs.get("foreground_package", obs.get("package"))
        if package is None:
            return _unknown("open_app predicate is missing expected package", obs, evidence)
        if _norm(actual_package) != _norm(package):
            return _fail(f"expected foreground package {package!r}, observed {actual_package!r}", obs, evidence)
        if activity is not None and _norm(obs.get("foreground_activity", obs.get("activity"))) != _norm(activity):
            return _fail(f"expected activity {activity!r}", obs, evidence)
        anchor = expected.get("ui_anchor")
        if anchor is not None and not (_contains(obs.get("visible_text"), anchor) or _contains(obs.get("resource_ids"), anchor)):
            return _unknown(f"package is correct but UI anchor {anchor!r} is not confirmed", obs, evidence)
        return _pass("expected app package is foreground", 0.98, obs, evidence)

    def _verify_tap(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        negative = expected.get("failure_conditions", [])
        for item in negative if isinstance(negative, Sequence) and not isinstance(negative, (str, bytes)) else []:
            if _contains_text(obs.get("visible_text"), str(item)):
                return _fail(f"failure condition observed: {item}", obs, evidence)

        target = expected.get("target")
        post_state = expected.get("post_state", expected.get("state"))
        target_present = False
        if target is not None:
            target_present = (
                _contains(obs.get("visible_text"), target)
                or _contains(obs.get("content_descriptions"), target)
                or _contains(obs.get("resource_ids"), target)
                or _contains(obs.get("node_ids"), target)
            )
        state_match = post_state is not None and (
            _norm(obs.get("screen")) == _norm(post_state)
            or _norm(obs.get("ui_state")) == _norm(post_state)
        )
        if target_present or state_match:
            return _pass("tap postcondition confirmed", 0.94 if target_present and state_match else 0.87, obs, evidence)
        if expected.get("allow_screen_change_only", False) and obs.get("screen_changed") is True:
            return _pass("screen change accepted by explicit predicate", 0.55, obs, evidence)
        return _fail("tap executed but expected UI target/state was not confirmed", obs, evidence)

    def _verify_search(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        query = str(expected.get("query", "")).strip()
        field_value = str(obs.get("search_query", obs.get("input_value", ""))).strip()
        if query and _norm(field_value) != _norm(query):
            return _fail(f"expected search query {query!r}, observed {field_value!r}", obs, evidence)
        if obs.get("result_state") in {"error", "network_error"}:
            return _fail(f"search failed with result state {obs.get('result_state')!r}", obs, evidence)
        required_state = expected.get("result_state", "loaded")
        if _norm(obs.get("result_state")) != _norm(required_state):
            return _unknown("search query is set but result state is not confirmed", obs, evidence)
        terms = expected.get("result_contains", query)
        if terms:
            wanted = terms if isinstance(terms, Sequence) and not isinstance(terms, (str, bytes)) else [terms]
            if not all(_contains_text(obs.get("result_text"), str(term)) for term in wanted):
                return _fail("search results do not satisfy expected relevance anchors", obs, evidence)
        return _pass("search result state and query are confirmed", 0.92, obs, evidence)

    def _verify_type(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        expected_value = str(expected.get("value", ""))
        observed_value = str(obs.get("input_value", ""))
        if observed_value == expected_value:
            return _pass("typed value confirmed", 0.95, obs, evidence)
        return _fail("typed value is not present in the expected input", obs, evidence)

    def _verify_open_url(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        expected_host = expected.get("host")
        actual_url = str(obs.get("url", ""))
        if expected_host and _norm(expected_host) not in _norm(actual_url):
            return _fail(f"expected URL host {expected_host!r}", obs, evidence)
        if expected.get("loaded", True) and obs.get("page_state") not in {"loaded", "interactive"}:
            return _unknown("URL is present but page is not confirmed loaded", obs, evidence)
        return _pass("expected URL/page is confirmed", 0.93, obs, evidence)

    def _verify_payment(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        authoritative_success = any(
            e.authoritative and e.confidence >= 0.90 and _norm(e.value) in {"success", "succeeded", "completed"}
            for e in evidence
        )
        provider_state = _norm(obs.get("provider_payment_state", obs.get("payment_state")))
        if provider_state in {"failed", "cancelled", "canceled"}:
            return _fail(f"payment provider reports {provider_state}", obs, evidence)
        if provider_state in {"success", "succeeded", "completed"} and authoritative_success:
            return _pass("payment success confirmed by authoritative provider evidence", 0.995, obs, evidence)
        if provider_state in {"processing", "pending", "requires_action", "authorization_required"}:
            return _unknown(f"payment is {provider_state}; final success is not confirmed", obs, evidence)
        if any(_contains_text(obs.get("visible_text"), term) for term in ("payment successful", "payment complete", "transaction successful")):
            return _unknown("payment UI suggests success, but authoritative confirmation is missing", obs, evidence)
        return _unknown("no authoritative payment success evidence", obs, evidence)

    def _verify_generic(self, expected: Mapping[str, Any], obs: Mapping[str, Any]) -> VerificationResult:
        evidence = _evidence(obs)
        for key, value in expected.items():
            if key in {"timeout_ms", "poll_interval_ms", "stability_window_ms", "failure_conditions"}:
                continue
            if obs.get(key) != value:
                return _fail(f"expected {key}={value!r}, observed {obs.get(key)!r}", obs, evidence)
        return _pass("expected predicate fields observed", 0.90, obs, evidence)
