from __future__ import annotations

from typing import Any, Mapping

from .success_predicates import SuccessPredicateEngine, VerificationResult, VerificationState


class ActionEffectVerifier:
    """Normalizes observations before action-specific verification.

    Transport ACKs are never treated as task success. Consequential payment
    actions additionally require authoritative provider terminal evidence.
    """

    def __init__(self) -> None:
        self.engine = SuccessPredicateEngine()

    @staticmethod
    def normalize(observation: Mapping[str, Any] | None) -> dict[str, Any]:
        obs = dict(observation or {})
        snapshot = obs.get("snapshot")
        if isinstance(snapshot, Mapping):
            merged = dict(snapshot)
            merged.update({k: v for k, v in obs.items() if k != "snapshot"})
            obs = merged
        package = obs.get("foreground_package") or obs.get("package") or obs.get("package_name")
        if package:
            obs["foreground_package"] = package

        tree = obs.get("tree")
        nodes = obs.get("nodes")
        flattened: list[Mapping[str, Any]] = []

        def walk(node: Any) -> None:
            if not isinstance(node, Mapping):
                return
            flattened.append(node)
            for child in node.get("children") or []:
                walk(child)

        if isinstance(tree, Mapping):
            walk(tree)
        if isinstance(nodes, list):
            flattened.extend(node for node in nodes if isinstance(node, Mapping))
        if flattened:
            visible = list(obs.get("visible_text") or [])
            descriptions = list(obs.get("content_descriptions") or [])
            resource_ids = list(obs.get("resource_ids") or [])
            node_ids = list(obs.get("node_ids") or [])
            for node in flattened:
                if node.get("password") or node.get("text") == "[REDACTED]":
                    continue
                if node.get("text"):
                    visible.append(str(node["text"]))
                if node.get("description") or node.get("content_description"):
                    descriptions.append(str(node.get("description") or node.get("content_description")))
                if node.get("view_id") or node.get("resource_id"):
                    resource_ids.append(str(node.get("view_id") or node.get("resource_id")))
                if node.get("node_id"):
                    node_ids.append(str(node["node_id"]))
            obs["visible_text"] = list(dict.fromkeys(visible))
            obs["content_descriptions"] = list(dict.fromkeys(descriptions))
            obs["resource_ids"] = list(dict.fromkeys(resource_ids))
            obs["node_ids"] = list(dict.fromkeys(node_ids))

        notification = obs.get("notification") or obs.get("notification_data")
        if isinstance(notification, Mapping):
            obs["notification_text"] = " ".join(str(x) for x in (notification.get("title"), notification.get("text")) if x)
            obs["notification_package"] = notification.get("package")
            obs["notification_id"] = notification.get("id")

        evidence = list(obs.get("evidence") or []) if isinstance(obs.get("evidence"), list) else []
        provider_status = obs.get("provider_status") or obs.get("provider_payment_state")
        if provider_status:
            evidence.append({
                "kind": "provider_state",
                "value": provider_status,
                "authoritative": bool(obs.get("provider_authoritative", False)),
                "confidence": 0.99 if obs.get("provider_authoritative") else 0.90,
                "source": obs.get("provider_source", "device_observation"),
            })
        if obs.get("transaction_id"):
            evidence.append({"kind": "transaction_id", "value": obs["transaction_id"], "confidence": 0.99})
        if obs.get("event_id"):
            evidence.append({"kind": "event_id", "value": obs["event_id"], "confidence": 0.99})
        obs["evidence"] = evidence
        return obs

    def verify(self, *, action_kind: str, expected: Mapping[str, Any], observation: Mapping[str, Any] | None) -> VerificationResult:
        normalized = self.normalize(observation)
        result = self.engine.verify(
            {"kind": action_kind, "success_predicate": dict(expected)},
            normalized,
        )

        # A payment is successful only when an authoritative provider reports
        # a terminal success state. A transaction ID alone or a UI message is
        # insufficient. This is intentionally deterministic and auditable.
        if action_kind in {"upi", "payment", "device_upi_payment"}:
            status = str(normalized.get("provider_status") or normalized.get("provider_payment_state") or "").casefold()
            authoritative = bool(normalized.get("provider_authoritative"))
            success_states = {str(x).casefold() for x in expected.get("success_states", ("success", "succeeded", "completed", "paid"))}
            if authoritative and status in success_states and normalized.get("transaction_id"):
                return VerificationResult(
                    VerificationState.VERIFIED,
                    "authoritative payment provider terminal success",
                    0.99,
                    tuple(result.evidence) + (type("Evidence", (), {"kind": "authoritative_provider"})(),),
                    normalized,
                )
            if status in {"pending", "processing", "requires_action", "authorization_required"}:
                return VerificationResult(VerificationState.UNKNOWN, "payment is not terminal", result.confidence, result.evidence, normalized)
            if status in {"failed", "declined", "cancelled", "canceled"}:
                return VerificationResult(VerificationState.FAILED, "payment provider reported failure", result.confidence, result.evidence, normalized)
            return VerificationResult(VerificationState.UNKNOWN, "no authoritative payment success evidence", result.confidence, result.evidence, normalized)
        return result
