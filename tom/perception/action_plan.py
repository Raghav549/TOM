from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .fusion import FusedTarget
from .multimodal_observation import UiNode


@dataclass(frozen=True)
class GroundedActionPlan:
    action: str
    node_id: str
    bounds: tuple[int, int, int, int]
    confidence: float
    requires_approval: bool
    evidence: tuple[str, ...]


class GroundedActionPlanner:
    """Turns trusted intent + observed evidence into a bounded action plan.

    It never executes the action and never derives the user's goal from screen text.
    """

    CONSEQUENT: ClassVar[frozenset[str]] = frozenset({
        "send_message", "send_email", "purchase", "payment", "delete", "account_change", "share_sensitive_data",
    })

    def choose_tap(
        self,
        intent: str,
        targets: list[FusedTarget],
        nodes: tuple[UiNode, ...],
        threshold: float = 0.72,
    ) -> GroundedActionPlan | None:
        del intent  # the caller's trusted intent is used for candidate generation
        for target in targets:
            if target.fused_score < threshold or not target.node_id or not target.bounds:
                continue
            node = next((n for n in nodes if n.node_id == target.node_id), None)
            if node is None or not node.enabled or not node.clickable:
                continue
            return GroundedActionPlan(
                action="tap_node",
                node_id=node.node_id,
                bounds=node.bounds,
                confidence=target.fused_score,
                requires_approval=False,
                evidence=target.evidence,
            )
        return None
