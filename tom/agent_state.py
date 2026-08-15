from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    RECOVERING = "recovering"
    ABORTED = "aborted"


@dataclass
class StepState:
    index: int
    tool: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    last_error: str | None = None
    last_fingerprint: str | None = None


@dataclass
class TaskState:
    conversation_id: str
    goal: str
    steps: list[StepState] = field(default_factory=list)
    current_index: int = 0
    max_attempts_per_step: int = 3
    max_total_steps: int = 40
    created_at: float = field(default_factory=monotonic)
    completed: bool = False

    def current(self) -> StepState | None:
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None

    def start_current(self) -> StepState | None:
        step = self.current()
        if step is None:
            return None
        step.status = StepStatus.RUNNING
        step.attempts += 1
        step.started_at = monotonic()
        return step

    def finish(self, success: bool, *, error: str | None = None, fingerprint: str | None = None) -> StepState | None:
        step = self.current()
        if step is None:
            return None
        step.status = StepStatus.SUCCEEDED if success else StepStatus.FAILED
        step.last_error = error
        step.last_fingerprint = fingerprint
        step.finished_at = monotonic()
        return step

    def recover_or_advance(self) -> str:
        step = self.current()
        if step is None:
            self.completed = True
            return "complete"
        if step.status is StepStatus.FAILED and step.attempts < self.max_attempts_per_step:
            step.status = StepStatus.RECOVERING
            return "retry"
        if step.status is StepStatus.SUCCEEDED:
            self.current_index += 1
            if self.current_index >= len(self.steps):
                self.completed = True
                return "complete"
            return "next"
        step.status = StepStatus.ABORTED
        return "abort"

    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(step.status is StepStatus.SUCCEEDED for step in self.steps)
        return done / len(self.steps)

    def public_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "goal": self.goal,
            "current_index": self.current_index,
            "progress": self.progress(),
            "completed": self.completed,
            "steps": [
                {
                    "index": step.index,
                    "tool": step.tool,
                    "status": step.status.value,
                    "attempts": step.attempts,
                    "last_error": step.last_error,
                    "last_fingerprint": step.last_fingerprint,
                }
                for step in self.steps
            ],
        }
