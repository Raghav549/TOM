from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ExplorationKind(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    SIDE_EFFECTING = "side_effecting"


@dataclass
class Checkpoint:
    task_id: str
    observation_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExplorationBudget:
    max_probes: int = 3
    probes_used: int = 0

    def consume(self) -> bool:
        if self.probes_used >= self.max_probes:
            return False
        self.probes_used += 1
        return True


class ExplorationController:
    """Bounded probing: exploration is never allowed to silently perform side effects."""

    def __init__(self, budget: ExplorationBudget | None = None) -> None:
        self.budget = budget or ExplorationBudget()
        self.checkpoints: list[Checkpoint] = []

    def checkpoint(self, checkpoint: Checkpoint) -> None:
        self.checkpoints.append(checkpoint)

    def can_probe(self, kind: ExplorationKind) -> bool:
        return kind in {ExplorationKind.READ_ONLY, ExplorationKind.REVERSIBLE} and self.budget.probes_used < self.budget.max_probes

    def probe(self, kind: ExplorationKind, operation: Callable[[], Any]) -> Any:
        if not self.can_probe(kind) or not self.budget.consume():
            raise PermissionError("exploration budget exhausted or operation is side-effecting")
        return operation()
