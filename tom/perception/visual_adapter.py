from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VisualRegion:
    label: str
    confidence: float
    bounds: tuple[int, int, int, int]


@dataclass(frozen=True)
class VisualAnalysis:
    model: str
    regions: tuple[VisualRegion, ...]
    raw: dict[str, Any] | None = None


class VisualModelAdapter(Protocol):
    async def analyze(self, image_ref: str, *, prompt: str) -> VisualAnalysis: ...


class DisabledVisualAdapter:
    """Explicit no-op adapter. It never fabricates visual results."""

    async def analyze(self, image_ref: str, *, prompt: str) -> VisualAnalysis:
        return VisualAnalysis(model="disabled", regions=(), raw={"available": False})
