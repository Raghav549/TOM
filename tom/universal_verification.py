from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .action_verification import ActionSpecificVerifier, PredicateResult
from .models import ToolCall, ToolResult


class RecoveryAction(StrEnum):
    VERIFIED = "verified"
    REGROUND = "re-ground"
    RETRY = "retry"
    ALTERNATE_ROUTE = "alternate_route"
    ASK_USER = "ask_user"
    ABORT = "abort"


@dataclass(frozen=True)
class UniversalVerification:
    predicate: PredicateResult
    recovery: RecoveryAction
    evidence_score: float
    reason: str


class UniversalActionVerifier:
    """Single decision point for Android, browser and provider-backed actions.

    A transport ACK or DOM/screen change is only execution evidence. A task can
    advance only when an action-specific postcondition has positive evidence.
    Unknown evidence triggers recovery rather than a false completion.
    """

    def __init__(self) -> None:
        self._verifier = ActionSpecificVerifier()

    def verify(
        self,
        call: ToolCall,
        result: ToolResult,
        *,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        provider: Mapping[str, Any] | None = None,
        attempt: int = 0,
        max_attempts: int = 2,
    ) -> UniversalVerification:
        predicate = self._verifier.verify(call, result, before=before, after=after, provider=provider)
        score = max(0.0, min(1.0, float(predicate.confidence)))
        if predicate.ok:
            return UniversalVerification(predicate, RecoveryAction.VERIFIED, score, predicate.reason)

        unknown = predicate.confidence > 0 and "no trustworthy" in predicate.reason.lower() or "not confirmed" in predicate.reason.lower()
        if unknown:
            if attempt == 0:
                return UniversalVerification(predicate, RecoveryAction.REGROUND, score, "positive evidence is missing; refresh UI/DOM/screenshot and re-ground")
            if attempt < max_attempts:
                return UniversalVerification(predicate, RecoveryAction.RETRY, score, "fresh evidence still inconclusive; retry the grounded action")
            return UniversalVerification(predicate, RecoveryAction.ASK_USER, score, "verification remained inconclusive after recovery attempts")

        if attempt < max_attempts:
            return UniversalVerification(predicate, RecoveryAction.ALTERNATE_ROUTE, score, "action-specific predicate failed; re-plan through another route")
        return UniversalVerification(predicate, RecoveryAction.ABORT, score, predicate.reason)

    @staticmethod
    def requires_strong_evidence(call: ToolCall) -> bool:
        name = call.name.casefold()
        return any(token in name for token in ("payment", "upi", "send", "delete", "publish", "purchase", "order", "book", "call", "video_call"))

    @staticmethod
    def merge_provider_evidence(observation: Mapping[str, Any], provider: Mapping[str, Any] | None) -> dict[str, Any]:
        merged = dict(observation)
        if not provider:
            return merged
        evidence = list(merged.get("evidence") or []) if isinstance(merged.get("evidence"), list) else []
        for key in ("status", "state", "transaction_status", "transaction_id", "recipient", "amount", "currency", "id", "event_id"):
            if key in provider and provider[key] is not None:
                evidence.append({
                    "kind": f"provider.{key}",
                    "value": provider[key],
                    "authoritative": key in {"status", "state", "transaction_status", "transaction_id"},
                    "confidence": 0.99 if key in {"status", "state", "transaction_status", "transaction_id"} else 0.92,
                    "source": "provider",
                })
        merged["evidence"] = evidence
        if provider.get("status") is not None:
            merged["provider_status"] = provider["status"]
        if provider.get("transaction_status") is not None:
            merged["provider_payment_state"] = provider["transaction_status"]
        if provider.get("transaction_id") is not None:
            merged["transaction_id"] = provider["transaction_id"]
        return merged
