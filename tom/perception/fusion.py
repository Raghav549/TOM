from __future__ import annotations

from dataclasses import dataclass

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
    """Combines independent semantic and visual evidence without inventing targets."""

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

    def fuse(self, nodes: tuple[UiNode, ...], visual: VisualAnalysis) -> list[FusedTarget]:
        fused: list[FusedTarget] = []
        for region in visual.regions:
            best: UiNode | None = None
            best_iou = 0.0
            for node in nodes:
                if node.bounds is None:
                    continue
                overlap = self._iou(node.bounds, region.bounds)
                if overlap > best_iou:
                    best_iou, best = overlap, node
            semantic = min(1.0, best_iou)
            combined = 0.55 * region.confidence + 0.45 * semantic
            fused.append(FusedTarget(
                node_id=best.node_id if best else None,
                label=region.label,
                bounds=best.bounds if best else region.bounds,
                semantic_score=semantic,
                visual_score=region.confidence,
                fused_score=combined,
                evidence=("visual", "ui_iou") if best else ("visual",),
            ))
        return sorted(fused, key=lambda item: item.fused_score, reverse=True)
