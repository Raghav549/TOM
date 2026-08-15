from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PerceptionSignal:
    source: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FusedObservation:
    timestamp_ms: int
    package_name: str | None
    window_id: int | None
    ui_tree: dict[str, Any] | None
    screenshot_ref: str | None
    signals: tuple[PerceptionSignal, ...]

    @property
    def confidence(self) -> float:
        if not self.signals:
            return 0.0
        return max(0.0, min(1.0, sum(s.confidence for s in self.signals) / len(self.signals)))


class PerceptionFusion:
    """Fuses semantic Android UI state and visual observations without inventing facts."""

    def fuse(
        self,
        *,
        timestamp_ms: int,
        package_name: str | None,
        window_id: int | None,
        ui_tree: dict[str, Any] | None,
        screenshot_ref: str | None,
        visual_confidence: float | None = None,
    ) -> FusedObservation:
        signals: list[PerceptionSignal] = []
        if ui_tree is not None:
            signals.append(PerceptionSignal("accessibility_ui", 0.95))
        if screenshot_ref is not None:
            signals.append(PerceptionSignal("screenshot", visual_confidence or 0.75))
        return FusedObservation(
            timestamp_ms=timestamp_ms,
            package_name=package_name,
            window_id=window_id,
            ui_tree=ui_tree,
            screenshot_ref=screenshot_ref,
            signals=tuple(signals),
        )

    @staticmethod
    def should_request_visual_fallback(observation: FusedObservation) -> bool:
        return observation.ui_tree is None or observation.confidence < 0.65
