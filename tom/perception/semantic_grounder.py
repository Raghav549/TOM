from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .multimodal_observation import MultimodalObservation, UiNode


@dataclass(frozen=True)
class GroundedTarget:
    node_id: str
    score: float
    reasons: tuple[str, ...]


class SemanticGrounder:
    """Grounds user intent against the fresh observed UI tree.

    It never treats arbitrary screen text as an instruction. The caller supplies
    the trusted intent; observed node content is evidence only.
    """

    def find(self, intent: str, observation: MultimodalObservation) -> list[GroundedTarget]:
        tokens = {t for t in re.findall(r"[\w@.-]+", intent.lower()) if len(t) > 1}
        results: list[GroundedTarget] = []
        for node in observation.nodes:
            evidence = " ".join(filter(None, [node.text, node.content_description, node.class_name])).lower()
            overlap = sum(1 for token in tokens if token in evidence)
            score = min(1.0, overlap / max(1, min(len(tokens), 4)))
            reasons = []
            if overlap:
                reasons.append(f"text_overlap:{overlap}")
            if node.enabled:
                reasons.append("enabled")
            if node.clickable:
                reasons.append("clickable")
            if score > 0:
                results.append(GroundedTarget(node.node_id, score, tuple(reasons)))
        return sorted(results, key=lambda item: item.score, reverse=True)

    def best(self, intent: str, observation: MultimodalObservation, threshold: float = 0.65) -> GroundedTarget | None:
        candidates = self.find(intent, observation)
        if not candidates or candidates[0].score < threshold:
            return None
        return candidates[0]
