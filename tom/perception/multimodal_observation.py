from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ScreenFrame:
    frame_id: str
    captured_at: str
    width: int
    height: int
    mime_type: str
    data_ref: str
    sha256: str


@dataclass(frozen=True)
class UiNode:
    node_id: str
    class_name: str | None = None
    text: str | None = None
    content_description: str | None = None
    bounds: tuple[int, int, int, int] | None = None
    clickable: bool = False
    editable: bool = False
    enabled: bool = True
    password: bool = False


@dataclass(frozen=True)
class MultimodalObservation:
    observation_id: str
    captured_at: str
    package_name: str | None
    window_id: int | None
    nodes: tuple[UiNode, ...] = field(default_factory=tuple)
    frame: ScreenFrame | None = None
    source: str = "android"

    @staticmethod
    def now(observation_id: str, package_name: str | None, nodes: tuple[UiNode, ...] = ()) -> "MultimodalObservation":
        return MultimodalObservation(
            observation_id=observation_id,
            captured_at=datetime.now(timezone.utc).isoformat(),
            package_name=package_name,
            window_id=None,
            nodes=nodes,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "captured_at": self.captured_at,
            "package_name": self.package_name,
            "window_id": self.window_id,
            "nodes": [node.__dict__ for node in self.nodes],
            "frame": self.frame.__dict__ if self.frame else None,
            "source": self.source,
        }
