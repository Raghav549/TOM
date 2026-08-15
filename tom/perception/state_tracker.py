from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class ScreenState:
    """Compact, stable representation of the device state used for replanning."""

    fingerprint: str
    package_name: str | None
    window_id: int | None
    node_count: int
    visible_text: tuple[str, ...]
    notification_count: int = 0


@dataclass(frozen=True)
class StateDelta:
    changed: bool
    package_changed: bool
    window_changed: bool
    structure_changed: bool
    text_changed: bool
    notification_changed: bool
    reasons: tuple[str, ...]


class ScreenStateTracker:
    """Detects meaningful screen transitions without trusting model claims."""

    def __init__(self) -> None:
        self._previous: ScreenState | None = None

    @staticmethod
    def _fingerprint(payload: Mapping[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return sha256(encoded.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def from_observation(observation: Mapping[str, Any]) -> ScreenState:
        nodes = observation.get("nodes") or []
        texts: list[str] = []
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            for key in ("text", "content_description"):
                value = str(node.get(key) or "").strip()
                if value and value not in texts and not node.get("password", False):
                    texts.append(value[:300])
        notifications = observation.get("notifications") or []
        stable = {
            "package": observation.get("package_name") or observation.get("package"),
            "window": observation.get("window_id"),
            "nodes": [
                {
                    "id": node.get("node_id") or node.get("id"),
                    "bounds": node.get("bounds"),
                    "text": "[REDACTED]" if node.get("password") else node.get("text"),
                    "desc": node.get("content_description") or node.get("description"),
                    "clickable": node.get("clickable"),
                    "editable": node.get("editable"),
                    "selected": node.get("selected"),
                    "focused": node.get("focused"),
                }
                for node in nodes
                if isinstance(node, Mapping)
            ],
            "notifications": len(notifications),
        }
        return ScreenState(
            fingerprint=ScreenStateTracker._fingerprint(stable),
            package_name=stable["package"],
            window_id=stable["window"],
            node_count=len(nodes),
            visible_text=tuple(texts[:200]),
            notification_count=len(notifications),
        )

    @staticmethod
    def compare(previous: ScreenState | None, current: ScreenState) -> StateDelta:
        if previous is None:
            return StateDelta(True, True, True, True, bool(current.visible_text), bool(current.notification_count), ("initial_observation",))
        reasons: list[str] = []
        package_changed = previous.package_name != current.package_name
        window_changed = previous.window_id != current.window_id
        structure_changed = previous.node_count != current.node_count or previous.fingerprint != current.fingerprint
        text_changed = previous.visible_text != current.visible_text
        notification_changed = previous.notification_count != current.notification_count
        if package_changed:
            reasons.append("package_changed")
        if window_changed:
            reasons.append("window_changed")
        if structure_changed:
            reasons.append("ui_structure_changed")
        if text_changed:
            reasons.append("visible_text_changed")
        if notification_changed:
            reasons.append("notification_count_changed")
        return StateDelta(bool(reasons), package_changed, window_changed, structure_changed, text_changed, notification_changed, tuple(reasons))

    def update(self, observation: Mapping[str, Any]) -> tuple[ScreenState, StateDelta]:
        current = self.from_observation(observation)
        delta = self.compare(self._previous, current)
        self._previous = current
        return current, delta

    def reset(self) -> None:
        self._previous = None
