from __future__ import annotations

from dataclasses import dataclass
import re

from .multimodal_observation import UiNode
from .visual_adapter import VisualAnalysis


@dataclass(frozen=True)
class FusedTarget:
    node_id: str | None
    label: str
    bounds: tuple[int, int, int, int] | None
    semantic_score: float
    visual_score: float
    fused_score: float
    evidence: tuple[str, ...]


class PerceptionFusion:
    """Fuse accessibility semantics and visual evidence without inventing targets.

    Structured semantics win when they identify a compatible control. Vision is used
    to recover controls missing or poorly labelled in the accessibility tree.
    """

    @staticmethod
    def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        area_a = max(1, ax2 - ax1) * max(1, ay2 - ay1)
        area_b = max(1, bx2 - bx1) * max(1, by2 - by1)
        return inter / float(area_a + area_b - inter)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}

    def _semantic_score(self, query: str, node: UiNode) -> float:
        query_tokens = self._tokens(query)
        node_text = " ".join(filter(None, (node.text, node.content_description, node.class_name)))
        node_tokens = self._tokens(node_text)
        overlap = len(query_tokens & node_tokens) / max(1, len(query_tokens))
        affordance = 0.15 if node.clickable or node.editable else 0.0
        visibility = 0.10 if node.enabled else -0.25
        return max(0.0, min(1.0, overlap + affordance + visibility))

    def ground(self, intent: str, nodes: tuple[UiNode, ...], visual: VisualAnalysis | None = None) -> list[FusedTarget]:
        """Return grounded candidates ordered by confidence."""
        candidates: list[FusedTarget] = []
        visual = visual or VisualAnalysis(model="none", regions=())

        # First-class accessibility candidates: no screenshot is required when semantics are sufficient.
        for node in nodes:
            if not node.enabled or node.password or node.bounds is None:
                continue
            score = self._semantic_score(intent, node)
            if score >= 0.25:
                label = node.text or node.content_description or node.class_name or "UI element"
                candidates.append(FusedTarget(
                    node_id=node.node_id,
                    label=label,
                    bounds=node.bounds,
                    semantic_score=score,
                    visual_score=0.0,
                    fused_score=min(1.0, 0.75 * score),
                    evidence=("accessibility",),
                ))

        # Visual fallback / corroboration.
        for region in visual.regions:
            best: UiNode | None = None
            best_iou = 0.0
            for node in nodes:
                if node.bounds is None or node.password:
                    continue
                overlap = self._iou(node.bounds, region.bounds)
                if overlap > best_iou:
                    best_iou, best = overlap, node
            semantic = min(1.0, best_iou)
            if best is not None:
                fused = 0.65 * region.confidence + 0.35 * semantic
                candidates.append(FusedTarget(
                    node_id=best.node_id,
                    label=region.label,
                    bounds=best.bounds,
                    semantic_score=semantic,
                    visual_score=region.confidence,
                    fused_score=fused,
                    evidence=("vision", "accessibility_overlap"),
                ))
            else:
                candidates.append(FusedTarget(
                    node_id=None,
                    label=region.label,
                    bounds=region.bounds,
                    semantic_score=0.0,
                    visual_score=region.confidence,
                    fused_score=0.60 * region.confidence,
                    evidence=("vision_fallback",),
                ))

        # De-duplicate the same semantic target, retaining the strongest evidence.
        by_node: dict[str, FusedTarget] = {}
        coordinate_only: list[FusedTarget] = []
        for candidate in candidates:
            if candidate.node_id is None:
                coordinate_only.append(candidate)
                continue
            existing = by_node.get(candidate.node_id)
            if existing is None or candidate.fused_score > existing.fused_score:
                by_node[candidate.node_id] = candidate
        return sorted([*by_node.values(), *coordinate_only], key=lambda item: item.fused_score, reverse=True)

    def fuse(self, nodes: tuple[UiNode, ...], visual: VisualAnalysis) -> list[FusedTarget]:
        # Backward-compatible alias for callers that already provide visual analysis.
        return self.ground("", nodes, visual)
