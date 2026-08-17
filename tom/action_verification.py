from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import ToolCall, ToolResult
from .success_predicates import SuccessPredicateEngine


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
    """Compatibility facade over the semantic SuccessPredicateEngine.

    The facade also normalizes legacy Android observations so older device
    adapters/tests still receive the same grounded semantics as the live
    runtime. Transport ACKs and screen changes alone are never treated as
    successful completion for consequential actions.
    """

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
                for key, target in (
                    ("text", visible),
                    ("content_description", descriptions),
                    ("resource_id", ids),
                    ("node_id", ids),
                ):
                    if node.get(key):
                        target.append(str(node[key]))
            obs.setdefault("visible_text", visible)
            obs.setdefault("content_descriptions", descriptions)
            obs.setdefault("resource_ids", ids)
            obs.setdefault("node_ids", ids)
        return obs

    @staticmethod
    def _legacy_expected(call: ToolCall) -> tuple[str, dict[str, Any]]:
        args = dict(call.arguments)
        name = call.name
        if name == "open_app":
            return name, {"package": args.get("expected_package", args.get("package_name"))}
        if name in {"tap", "tap_node"}:
            return name, {
                "target": args.get("expected_text", args.get("expected_target")),
                "expected_package": args.get("expected_package"),
                "post_state": args.get("post_state"),
            }
        if name in {"search_google", "device_search_google"}:
            return "search", {
                "query": args.get("query", ""),
                "result_state": args.get("result_state", "loaded"),
                "result_contains": args.get("result_contains", []),
            }
        if name in {"set_text_node", "device_type"}:
            return "type", {"value": args.get("text", "")}
        if name in {
            "send_message",
            "send_email",
            "send_sms",
            "send_form",
            "communication.sms_send",
            "google.gmail_send",
        }:
            return "send", {}
        if name in {"create_calendar_event", "device_create_calendar_event"}:
            return "create_calendar_event", {"title": args.get("title", "")}
        if name in {"device_upi_payment", "upi_payment"}:
            return "upi", {}
        return name, {}

    @staticmethod
    def _infer_search_loaded(observation: dict[str, Any], query: str) -> None:
        """Infer a loaded result state only from grounded result evidence.

        Some legacy Android adapters expose accessibility nodes but do not yet
        emit an explicit ``result_state``. We accept that representation only
        when the observed UI contains the query's meaningful tokens plus a
        result-like anchor. A generic browser/Google screen therefore cannot
        satisfy the predicate by itself.
        """
        if observation.get("result_state") or observation.get("search_state"):
            return
        visible = observation.get("visible_text", [])
        if not isinstance(visible, list) or not query.strip():
            return
        blob = " ".join(str(x) for x in visible).casefold()
        query_tokens = [token for token in query.casefold().replace("/", " ").replace("-", " ").split() if len(token) > 1]
        if not query_tokens:
            return
        matched = sum(1 for token in set(query_tokens) if token in blob)
        result_anchor = any(anchor in blob for anchor in ("search results", "results", "result"))
        coverage = matched / len(set(query_tokens))
        if result_anchor and coverage >= 0.5 and len(visible) >= 2:
            observation["result_state"] = "loaded"

    def verify(
        self,
        call: ToolCall,
        result: ToolResult,
        *,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        provider: Mapping[str, Any] | None = None,
    ) -> PredicateResult:
        if not result.success:
            return PredicateResult(False, "tool_success", 0.0, (), result.error or "tool failed")

        kind, expected = self._legacy_expected(call)
        normalized_after = self._normalize_observation(after)

        if kind == "search":
            self._infer_search_loaded(normalized_after, str(expected.get("query", "")))

        if provider:
            normalized_after.setdefault("evidence", [])
            if isinstance(normalized_after["evidence"], list):
                for key, value in provider.items():
                    if key in {"status", "state", "transaction_status", "transaction_id", "id", "event_id"}:
                        normalized_after["evidence"].append(
                            {
                                "kind": "provider",
                                "value": value,
                                "authoritative": key in {"status", "state", "transaction_status"},
                                "confidence": 0.99,
                            }
                        )
                if provider.get("status"):
                    normalized_after["provider_status"] = provider["status"]
                    normalized_after["provider_payment_state"] = provider["status"]
                if provider.get("id") or provider.get("event_id"):
                    normalized_after["event_id"] = provider.get("id", provider.get("event_id"))
                if provider.get("transaction_id"):
                    normalized_after["transaction_id"] = provider["transaction_id"]

        if kind == call.name and not expected:
            return PredicateResult(
                True,
                "tool_success",
                0.75,
                ("tool_result",),
                "tool returned a successful result",
            )

        verification = self._engine.verify(
            {"kind": kind, "success_predicate": expected},
            normalized_after,
        )

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

        # An exact package observation from the Android accessibility/runtime
        # state is deterministic for this compatibility API. Keep the engine's
        # stricter confidence for UI-anchor/activity variants.
        if kind == "open_app":
            wanted = expected.get("package")
            observed = normalized_after.get(
                "foreground_package",
                normalized_after.get("package", normalized_after.get("package_name", "")),
            )
            if wanted and str(wanted).strip().casefold() == str(observed).strip().casefold() and not expected.get("activity") and not expected.get("ui_anchor"):
                verification = type(verification)(
                    verification.state,
                    verification.reason,
                    1.0,
                    verification.evidence,
                    verification.observed,
                )

        # Pending/processing UPI is a distinct verified observation of the
        # provider state, but it is deliberately NOT task success. Exposing a
        # state-specific predicate keeps the runtime and diagnostics truthful.
        if kind == "upi":
            provider_state = str(
                normalized_after.get("provider_payment_state", "")
            ).strip().casefold()
            if provider_state in {"pending", "processing", "requires_action", "authorization_required"}:
                predicate = "upi.pending"
            elif provider_state in {"failed", "cancelled", "canceled", "declined"}:
                predicate = "upi.provider_failure"
            elif provider_state in {"success", "succeeded", "completed", "paid"}:
                predicate = "upi.provider_success"

        return PredicateResult(
            verification.verified,
            predicate,
            verification.confidence,
            tuple(e.kind for e in verification.evidence),
            verification.reason,
        )
