from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CropRegion:
    x1: int
    y1: int
    x2: int
    y2: int

    def valid(self, width: int, height: int) -> bool:
        return 0 <= self.x1 < self.x2 <= width and 0 <= self.y1 < self.y2 <= height


class PrivacyCropPolicy:
    """Defines regions that must be excluded before remote visual analysis.

    Detection is deliberately supplied by trusted local detectors; this module
    never guesses that an arbitrary region is safe to transmit.
    """

    def __init__(self, blocked: tuple[CropRegion, ...] = ()) -> None:
        self.blocked = blocked

    def allowed(self, width: int, height: int) -> tuple[CropRegion, ...]:
        return tuple(region for region in self.blocked if region.valid(width, height))
