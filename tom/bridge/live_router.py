from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .live_protocol import BridgeEnvelope


@dataclass
class PendingAction:
    task_id: str
    action_id: str
    observation_request_id: str | None = None
    acked: bool = False


class LiveBridgeRouter:
    """Routes authenticated live Android envelopes to task waiters.

    Transport ownership remains with the WebSocket endpoint. This component
    only accepts already-authenticated envelopes and correlates events.
    """

    def __init__(self) -> None:
        self.pending: dict[str, PendingAction] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self.screens: dict[str, dict[int, dict[str, Any]]] = {}
        self.last_sequence: dict[str, int] = {}

    def accept_sequence(self, envelope: BridgeEnvelope) -> bool:
        last = self.last_sequence.get(envelope.device_id, -1)
        if envelope.sequence <= last:
            return False
        self.last_sequence[envelope.device_id] = envelope.sequence
        return True

    def register_action(self, task_id: str, action_id: str) -> None:
        self.pending[action_id] = PendingAction(task_id, action_id)

    def handle(self, envelope: BridgeEnvelope) -> dict[str, Any] | None:
        if not self.accept_sequence(envelope):
            return None
        if envelope.type in {"ACTION_ACK", "ACTION_RESULT"}:
            action_id = envelope.payload.get("action_id") or envelope.correlation_id
            pending = self.pending.get(action_id)
            if not pending:
                return None
            if envelope.type == "ACTION_ACK":
                pending.acked = True
            return {"event": "action", "action_id": action_id, "payload": envelope.payload}

        if envelope.type == "OBSERVATION":
            correlation = envelope.correlation_id or envelope.payload.get("observation_id")
            if not isinstance(correlation, str):
                return None
            self.observations[correlation] = envelope.payload
            return {"event": "observation", "correlation_id": correlation, "payload": envelope.payload}

        if envelope.type == "SCREENSHOT_CHUNK":
            transfer = envelope.payload.get("transfer_id")
            index = envelope.payload.get("index")
            if not isinstance(transfer, str) or not isinstance(index, int):
                return None
            self.screens.setdefault(transfer, {})[index] = envelope.payload
            return {"event": "screenshot_chunk", "transfer_id": transfer, "index": index}

        return {"event": envelope.type.lower(), "payload": envelope.payload}
