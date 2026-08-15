from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

ALLOWED_TYPES = {
    "HELLO", "HELLO_ACK", "ACTION_REQUEST", "ACTION_ACK", "ACTION_RESULT",
    "OBSERVATION_REQUEST", "OBSERVATION", "SCREENSHOT_CHUNK", "ERROR", "HEARTBEAT"
}


@dataclass(frozen=True)
class BridgeEnvelope:
    type: str
    device_id: str
    session_id: str
    sequence: int
    correlation_id: str | None
    payload: dict[str, Any]

    def encode(self) -> str:
        if self.type not in ALLOWED_TYPES:
            raise ValueError("unsupported bridge message type")
        if self.sequence < 0:
            raise ValueError("invalid sequence")
        return json.dumps({
            "v": 1,
            "type": self.type,
            "device_id": self.device_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }, separators=(",", ":"))

    @staticmethod
    def decode(raw: str) -> BridgeEnvelope:
        obj = json.loads(raw)
        if obj.get("v") != 1 or obj.get("type") not in ALLOWED_TYPES:
            raise ValueError("invalid bridge envelope")
        device_id = obj.get("device_id")
        session_id = obj.get("session_id")
        sequence = obj.get("sequence")
        payload = obj.get("payload")
        if not isinstance(device_id, str) or not isinstance(session_id, str):
            raise TypeError("missing bridge identity")
        if not isinstance(sequence, int) or sequence < 0 or not isinstance(payload, dict):
            raise ValueError("invalid bridge envelope fields")
        return BridgeEnvelope(obj["type"], device_id, session_id, sequence, obj.get("correlation_id"), payload)
