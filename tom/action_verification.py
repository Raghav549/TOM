from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import ToolCall, ToolResult
from .strict_success_predicates import StrictSuccessPredicateEngine
from .universal_action_contract import ActionType, build_action
from .universal_verifier import verify_universal


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
    """Single verification facade shared by runtime, Android and browser actions."""

    def __init__(self) -> None:
        self._engine = StrictSuccessPredicateEngine()

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
            obs.setdefault("node_ids", ids)
        return obs

    @staticmethod
    def _legacy_expected(call: ToolCall) -> tuple[str, dict[str, Any]]:
        args = dict(call.arguments)
        name = call.name
        if name == "open_app":
            return name, {"package": args.get("expected_package", args.get("package_name")), "activity": args.get("expected_activity"), "ui_anchor": args.get("ui_anchor")}
        if name in {"tap", "tap_node"}:
            return "tap", {"target": args.get("expected_text", args.get("expected_target", args.get("target_text"))), "expected_package": args.get("expected_package"), "post_state": args.get("post_state")}
        if name in {"search_google", "device_search_google"}:
            return "search", {"query": args.get("query", ""), "result_state": args.get("result_state", "loaded"), "result_contains": args.get("result_contains", [])}
        if name in {"set_text_node", "device_type"}:
            return "type", {"value": args.get("text", "")}
        if name in {"send_message", "send_email", "send_sms", "send_form", "communication.sms_send", "google.gmail_send"}:
            return "send", {"recipient": args.get("recipient", ""), "body": args.get("body", args.get("message", args.get("text", "")))}
        if name in {"create_calendar_event", "device_create_calendar_event"}:
            return "create_calendar_event", {"title": args.get("title", "")}
        if name in {"device_upi_payment", "upi_payment"}:
            return "upi", {"provider": args.get("provider", ""), "amount": args.get("amount", args.get("am")), "recipient": args.get("recipient", args.get("pn", args.get("pa", "")))}
        return name, {}

    @staticmethod
    def _infer_search_loaded(observation: dict[str, Any], query: str) -> None:
        if observation.get("result_state") or observation.get("search_state"):
            return
        visible = observation.get("visible_text", [])
        if not isinstance(visible, list) or not query.strip():
            return
        blob = " ".join(str(x) for x in visible).casefold()
        query_tokens = [token for token in query.casefold().replace("/", " ").replace("-", " ").split() if len(token) > 1]
        unique_tokens = set(query_tokens)
        if not unique_tokens:
            return
        matched = sum(1 for token in unique_tokens if token in blob)
        result_anchor = any(anchor in blob for anchor in ("search results", "results", "result"))
        if result_anchor and matched / len(unique_tokens) >= 0.5 and len(visible) >= 2:
            observation["result_state"] = "loaded"
            observation["search_query"] = query

    @staticmethod
    def _ui_send_evidence(observation: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
        values: list[str] = []
        for key in ("visible_text", "content_descriptions", "notification_text", "page_text"):
            value = observation.get(key, [])
            if isinstance(value, (list, tuple)):
                values.extend(str(item) for item in value)
            elif value:
                values.append(str(value))
        blob = " ".join(values).casefold()
        positive = any(token in blob for token in ("message sent", "sent successfully", "message delivered", "email sent", "sms sent"))
        negative = any(token in blob for token in ("failed to send", "couldn't send", "could not send", "not sent", "send failed"))
        return positive and not negative, ("positive_send_confirmation",) if positive and not negative else ()

    @staticmethod
    def _upi_state(observation: Mapping[str, Any]) -> str:
        for key in ("provider_payment_state", "payment_state", "provider_status", "status", "transaction_status"):
            value = observation.get(key)
            if value is not None and str(value).strip():
                return str(value).strip().casefold()
        return ""

    def _verify_upi(self, call: ToolCall, expected: Mapping[str, Any], observation: Mapping[str, Any]) -> PredicateResult:
        state = self._upi_state(observation)
        transaction_id = str(observation.get("transaction_id", observation.get("utr", observation.get("txn_id", "")))).strip()
        evidence = observation.get("evidence", ())
        has_authoritative_success = False
        if isinstance(evidence, (list, tuple)):
            for item in evidence:
                if not isinstance(item, Mapping):
                    continue
                value = str(item.get("value", "")).strip().casefold()
                try:
                    confidence = float(item.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                if item.get("authoritative") is True and confidence >= 0.90 and value in {"success", "succeeded", "completed", "paid"}:
                    has_authoritative_success = True
                    break
        if state in {"pending", "processing", "queued", "initiated", "requires_action", "authorization_required"}:
            return PredicateResult(False, "upi.pending", 0.99, ("payment_state",), f"payment remains {state}")
        if state in {"failed", "declined", "cancelled", "canceled", "error", "reversed"}:
            return PredicateResult(False, "upi.provider_failure", 1.0, ("payment_state",), f"payment state is {state}")
        if state in {"success", "succeeded", "completed", "paid"} and not (transaction_id or has_authoritative_success):
            return PredicateResult(False, "upi.provider_evidence", 0.99, ("payment_state",), "terminal success state lacks transaction/provider evidence")
        hard = verify_universal(call.name, expected, observation)
        if hard is not None:
            ok, confidence, reason, hard_evidence = hard
            if ok:
                return PredicateResult(True, "upi.provider_success", confidence, hard_evidence, reason)
            return PredicateResult(False, "upi.provider_evidence", confidence, hard_evidence, reason)
        return PredicateResult(False, "upi.provider_evidence", 0.0, (), "authoritative payment evidence not confirmed")

    def verify(self, call: ToolCall, result: ToolResult, *, before: Mapping[str, Any] | None = None, after: Mapping[str, Any] | None = None, provider: Mapping[str, Any] | None = None) -> PredicateResult:
        if not result.success:
            return PredicateResult(False, "tool_success", 0.0, (), result.error or "tool failed")
        provider_data = dict(provider or {})
        device_verification = provider_data.get("device_verification")
        if isinstance(device_verification, Mapping):
            status = str(device_verification.get("status", "")).casefold()
            if status == "verified":
                return PredicateResult(True, str(device_verification.get("predicate") or call.name), float(device_verification.get("confidence", 1.0)), tuple(str(x) for x in device_verification.get("evidence", [])), str(device_verification.get("reason", "authoritative device verification passed")))
            if status in {"failed", "unknown"}:
                return PredicateResult(False, str(device_verification.get("predicate") or call.name), float(device_verification.get("confidence", 0.0)), tuple(str(x) for x in device_verification.get("evidence", [])), str(device_verification.get("reason", f"device verification {status}")))
        kind, expected = self._legacy_expected(call)
        try:
            contract_type = ActionType(call.name)
            contract = build_action(str(call.arguments.get("action_id", call.name)), str(call.arguments.get("task_id", "")), contract_type, dict(call.arguments))
            expected = {**contract.predicate.expected, **expected}
            kind = contract_type.value
        except ValueError:
            pass
        normalized_after = self._normalize_observation(after)
        if kind == "search":
            self._infer_search_loaded(normalized_after, str(expected.get("query", "")))
        if provider_data:
            normalized_after.setdefault("evidence", [])
            if isinstance(normalized_after["evidence"], list):
                for key, value in provider_data.items():
                    if key in {"status", "state", "transaction_status", "transaction_id", "id", "event_id", "provider_event_id"}:
                        normalized_after["evidence"].append({"kind": "provider", "value": value, "authoritative": key in {"status", "state", "transaction_status"}, "confidence": 0.99})
            if provider_data.get("status"):
                normalized_after["provider_status"] = provider_data["status"]
                normalized_after["provider_payment_state"] = provider_data["status"]
            if provider_data.get("transaction_id"):
                normalized_after["transaction_id"] = provider_data["transaction_id"]
            if provider_data.get("id"):
                normalized_after["event_id"] = provider_data["id"]
            if provider_data.get("event_id"):
                normalized_after["event_id"] = provider_data["event_id"]
            if provider_data.get("provider_event_id"):
                normalized_after["event_id"] = provider_data["provider_event_id"]
        if kind == "upi":
            return self._verify_upi(call, expected, normalized_after)
        if kind in {"send", "send_message"}:
            ui_ok, ui_evidence = self._ui_send_evidence(normalized_after)
            if ui_ok:
                return PredicateResult(True, "universal.send_message", 0.97, ui_evidence, "positive send confirmation visible")
        hard = verify_universal(call.name, expected, normalized_after)
        if hard is not None:
            ok, confidence, reason, evidence = hard
            if kind == "create_calendar_event":
                predicate = "calendar.event_created"
            elif kind in {"send", "send_message"}:
                predicate = "universal.send_message"
            else:
                predicate = f"universal.{call.name}"
            return PredicateResult(ok, predicate, confidence, evidence, reason)
        if kind == "create_calendar_event":
            event_id = str(normalized_after.get("event_id", "")).strip()
            if event_id:
                return PredicateResult(True, "calendar.event_created", 0.99, ("event_id",), "calendar provider event id confirmed")
            return PredicateResult(False, "calendar.event_created", 0.0, (), "calendar creation is not confirmed")
        if kind == call.name and not expected:
            return PredicateResult(True, "tool_success", 0.75, ("tool_result",), "tool returned a successful result")
        verification = self._engine.verify({"kind": kind, "success_predicate": expected}, normalized_after)
        predicate = {"open_app": "open_app.expected_package", "tap": "tap.expected_ui_target", "tap_node": "tap.expected_ui_target", "search": "search.expected_result_state", "type": "set_text.expected_value", "send": "universal.send_message", "send_message": "universal.send_message", "create_calendar_event": "calendar.event_created", "upi": "upi.provider_success"}.get(kind, "tool_success")
        if kind == "open_app":
            wanted = expected.get("package")
            observed = normalized_after.get("foreground_package", normalized_after.get("package", normalized_after.get("package_name", "")))
            if wanted and str(wanted).strip().casefold() == str(observed).strip().casefold() and not expected.get("activity") and not expected.get("ui_anchor"):
                verification = type(verification)(verification.state, verification.reason, 1.0, verification.evidence, verification.observed)
        return PredicateResult(verification.verified, predicate, verification.confidence, tuple(e.kind for e in verification.evidence), verification.reason)
