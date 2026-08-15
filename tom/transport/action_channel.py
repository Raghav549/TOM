from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionCommand:
    action_id: str
    device_id: str
    capability: str
    operation: str
    arguments: dict[str, Any]
    approval_id: str | None = None
    expected_state: dict[str, Any] | None = None


@dataclass(frozen=True)
class ActionAcknowledgement:
    action_id: str
    accepted: bool
    message: str


@dataclass(frozen=True)
class ActionOutcome:
    action_id: str
    status: str
    evidence: dict[str, Any]


class ActionChannel:
    """Validates command shape; execution remains on the authenticated device adapter."""

    def validate(self, command: ActionCommand) -> None:
        if not command.action_id or not command.device_id:
            raise ValueError("action_id and device_id are required")
        if not command.capability or not command.operation:
            raise ValueError("capability and operation are required")
        if command.capability.startswith("android.") and not command.arguments:
            raise ValueError("android actions require explicit arguments")

    def acknowledgement(self, command: ActionCommand, accepted: bool, message: str) -> ActionAcknowledgement:
        self.validate(command)
        return ActionAcknowledgement(command.action_id, accepted, message)
