from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ScreenObservation:
    """A single synchronized view of the device for agent grounding."""

    package_name: str | None
    window_id: int | None
    ui_tree: dict[str, Any] | None = None
    screenshot_ref: str | None = None
    timestamp_ms: int | None = None
    redactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundedTarget:
    target_id: str
    action: str
    confidence: float
    evidence: tuple[str, ...] = ()
    coordinates: tuple[float, float] | None = None


@dataclass
class ObservationBuffer:
    max_items: int = 12
    _items: list[ScreenObservation] = field(default_factory=list)

    def add(self, observation: ScreenObservation) -> None:
        self._items.append(observation)
        if len(self._items) > self.max_items:
            del self._items[: len(self._items) - self.max_items]

    def latest(self) -> ScreenObservation | None:
        return self._items[-1] if self._items else None

    def recent(self) -> list[ScreenObservation]:
        return list(self._items)


class ScreenPerceiver(Protocol):
    async def describe(self, observation: ScreenObservation) -> dict[str, Any]: ...


class ActionGrounder(Protocol):
    async def ground(
        self,
        observation: ScreenObservation,
        requested_action: str,
        target: str,
    ) -> GroundedTarget | None: ...
