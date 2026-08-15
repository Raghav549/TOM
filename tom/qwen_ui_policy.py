from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PerceptionMode(str, Enum):
    SEMANTIC = "semantic"
    VISUAL = "visual"
    FUSED = "fused"


@dataclass(frozen=True)
class UIPolicyDecision:
    mode: PerceptionMode
    reason: str
    allow_batch: bool
    require_fresh_observation: bool = True
    require_visual_refinement: bool = False


@dataclass(frozen=True)
class QwenUIPolicy:
    """Small deterministic policy layer implementing research-backed routing principles.

    This is deliberately not presented as the learned UI-UX model itself. It operationalizes
    the paper findings in TOM's runtime: fuse semantics and pixels, route visual reasoning to
    uncertain/dense interfaces, refine coordinates, and keep consequential actions single-step.
    """

    dense_node_threshold: int = 80

    def decide(self, *, node_count: int, has_screenshot: bool, target_confidence: float,
               action_risk: str, screen_changed: bool = False) -> UIPolicyDecision:
        uncertain = target_confidence < 0.82
        dense = node_count >= self.dense_node_threshold
        consequential = action_risk in {"high", "critical"}

        if screen_changed:
            return UIPolicyDecision(
                PerceptionMode.FUSED if has_screenshot else PerceptionMode.SEMANTIC,
                "screen changed; discard stale grounding and re-observe",
                allow_batch=False,
                require_fresh_observation=True,
                require_visual_refinement=has_screenshot,
            )
        if has_screenshot and (uncertain or dense):
            return UIPolicyDecision(
                PerceptionMode.FUSED,
                "uncertain or dense UI; use semantic candidates plus visual coarse-to-fine refinement",
                allow_batch=False,
                require_fresh_observation=True,
                require_visual_refinement=True,
            )
        return UIPolicyDecision(
            PerceptionMode.SEMANTIC if not has_screenshot else PerceptionMode.FUSED,
            "stable grounded target",
            allow_batch=not consequential,
            require_fresh_observation=True,
            require_visual_refinement=False,
        )

    @staticmethod
    def sanitize_visual_regions(regions: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
        """Keep only finite, in-frame regions before they can influence an action."""
        safe: list[dict[str, Any]] = []
        for region in regions:
            try:
                x1, y1, x2, y2 = (int(v) for v in region["bounds"])
                confidence = float(region.get("confidence", 0))
                label = str(region.get("label", "")).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if not label or not 0 <= confidence <= 1:
                continue
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 <= x1 or y2 <= y1:
                continue
            safe.append({"label": label, "confidence": confidence, "bounds": [x1, y1, x2, y2]})
        return sorted(safe, key=lambda item: item["confidence"], reverse=True)
