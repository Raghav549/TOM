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
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)
    provider_evidence: dict[str, Any] = field(default_factory=dict)
    last_verification: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    def observe(
        self,
        *,
        package: str | None = None,
        url: str | None = None,
        fingerprint: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        if state is not None:
            if self.after_state:
                self.before_state = dict(self.after_state)
            self.after_state = dict(state)
        self.current_app = package or self.current_app
        self.current_url = url or self.current_url
        self.screen_fingerprint = fingerprint or self.screen_fingerprint
        self.observation_version += 1

    def action_started(self, action_id: str) -> None:
        self.last_action_id = action_id
        self.last_action_status = "running"
        self.last_error = None
        self.provider_evidence = {}
        self.last_verification = {}
        self.before_state = dict(self.after_state)

    def action_finished(self, success: bool, error: str | None = None) -> None:
        self.last_action_status = "succeeded" if success else "failed"
        self.last_error = error

    def record_verification(
        self,
        verdict: dict[str, Any],
        *,
        after_state: dict[str, Any] | None = None,
        provider_evidence: dict[str, Any] | None = None,
    ) -> None:
        self.last_verification = dict(verdict)
        if after_state is not None:
            self.after_state = dict(after_state)
        if provider_evidence is not None:
            self.provider_evidence = dict(provider_evidence)
        self.variables["last_predicate"] = verdict.get("predicate")
        self.variables["last_verification_confidence"] = verdict.get("confidence", 0.0)

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
            "before_state": dict(self.before_state),
            "after_state": dict(self.after_state),
            "provider_evidence": dict(self.provider_evidence),
            "last_verification": dict(self.last_verification),
            "variables": dict(self.variables),
        }
