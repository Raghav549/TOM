from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field

from .screenshot_transport import MAX_FRAME_BYTES


@dataclass
class _Transfer:
    total: int
    sha256: str
    chunks: dict[int, bytes] = field(default_factory=dict)


class ScreenshotReassembler:
    def __init__(self, max_frame_bytes: int = MAX_FRAME_BYTES) -> None:
        self.max_frame_bytes = max_frame_bytes
        self._transfers: dict[str, _Transfer] = {}

    def accept(self, *, transfer_id: str, index: int, total: int, sha256: str, data_b64: str) -> bytes | None:
        if not transfer_id or total < 1 or total > 1000 or index < 0 or index >= total:
            raise ValueError("invalid screenshot chunk metadata")
        raw = base64.b64decode(data_b64, validate=True)
        if len(raw) > 256 * 1024:
            raise ValueError("chunk too large")
        transfer = self._transfers.setdefault(transfer_id, _Transfer(total, sha256))
        if transfer.total != total or transfer.sha256 != sha256:
            self._transfers.pop(transfer_id, None)
            raise ValueError("screenshot transfer metadata mismatch")
        transfer.chunks[index] = raw
        if len(transfer.chunks) != total:
            return None
        data = b"".join(transfer.chunks[i] for i in range(total))
        self._transfers.pop(transfer_id, None)
        if len(data) > self.max_frame_bytes:
            raise ValueError("reassembled screenshot too large")
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError("screenshot digest mismatch")
        return data
