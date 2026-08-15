from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionRequest:
    task_id: str
    capability: str
    requester: str
    reason: str
    sensitive: bool = False


class TaskPermissionAuthorizer:
    """Keep OS permission decisions separate from task completion reasoning."""

    def evaluate(self, request: PermissionRequest) -> str:
        if not request.task_id.strip() or not request.capability.strip():
            return "deny"
        if request.sensitive:
            return "ask_user"
        return "allow_if_granted"
