from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GroundingMethod(str, Enum):
    ACCESSIBILITY_NODE = "accessibility_node"
    NATIVE_API = "native_api"
    BROWSER = "browser"
    GESTURE = "gesture"
    VISUAL = "visual"


@dataclass(frozen=True)
class GroundingCandidate:
    target_id: str
    method: GroundingMethod
    confidence: float
    evidence: tuple[str, ...] = ()


class GroundingError(RuntimeError):
    pass


class ActionGrounder:
    """Selects a real UI target; never fabricates a coordinate or node id."""

    def choose(self, candidates: list[GroundingCandidate], threshold: float = 0.80) -> GroundingCandidate:
        if not candidates:
            raise GroundingError("no actionable target was observed")
        ranked = sorted(candidates, key=lambda item: item.confidence, reverse=True)
        best = ranked[0]
        if best.confidence < threshold:
            raise GroundingError("target confidence is below safe execution threshold")
        return best
