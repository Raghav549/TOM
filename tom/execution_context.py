from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveExecutionContext:
    """Authoritative, bounded state shared by planner, device, voice and UI."""

    task_id: str
    goal: str
    current_app: str | None = None
    current_url: str | None = None
    screen_fingerprint: str | None = None
    observation_version: int = 0
    last_action_id: str | None = None
    last_action_status: str | None = None
    last_error: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)

    def observe(self, *, package: str | None = None, url: str | None = None,
                fingerprint: str | None = None) -> None:
        self.current_app = package or self.current_app
        self.current_url = url or self.current_url
        self.screen_fingerprint = fingerprint or self.screen_fingerprint
        self.observation_version += 1

    def action_started(self, action_id: str) -> None:
        self.last_action_id = action_id
        self.last_action_status = "running"
        self.last_error = None

    def action_finished(self, success: bool, error: str | None = None) -> None:
        self.last_action_status = "succeeded" if success else "failed"
        self.last_error = error

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "current_app": self.current_app,
            "current_url": self.current_url,
            "screen_fingerprint": self.screen_fingerprint,
            "observation_version": self.observation_version,
            "last_action_id": self.last_action_id,
            "last_action_status": self.last_action_status,
            "last_error": self.last_error,
            "variables": dict(self.variables),
        }
