from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any


class TaskState(str, Enum):
    RECEIVED = "received"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    OBSERVING = "observing"
    ACTING = "acting"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskStateMachine:
    task_id: str
    state: TaskState = TaskState.RECEIVED
    step_index: int = 0
    attempts: int = 0
    context: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time)

    def transition(self, state: TaskState, **context: Any) -> None:
        self.state = state
        self.context.update(context)
        self.updated_at = time()

    def next_step(self) -> int:
        self.step_index += 1
        self.attempts = 0
        self.updated_at = time()
        return self.step_index

    def retry(self) -> int:
        self.attempts += 1
        self.updated_at = time()
        return self.attempts

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "step_index": self.step_index,
            "attempts": self.attempts,
            "context": dict(self.context),
            "updated_at": self.updated_at,
        }
