from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field

from .screenshot_transport import MAX_FRAME_BYTES, ScreenshotChunk


@dataclass
class ScreenshotReassembler:
    transfer_id: str
    total: int
    expected_sha256: str
    _parts: dict[int, bytes] = field(default_factory=dict)

    def add(self, chunk: ScreenshotChunk) -> bool:
        if chunk.transfer_id != self.transfer_id or chunk.total != self.total:
            raise ValueError("screenshot transfer mismatch")
        if not 0 <= chunk.index < self.total:
            raise ValueError("invalid screenshot chunk index")
        if len(chunk.data_b64) > MAX_FRAME_BYTES * 2:
            raise ValueError("screenshot chunk is too large")
        data = base64.b64decode(chunk.data_b64, validate=True)
        if len(data) > 256 * 1024:
            raise ValueError("screenshot chunk exceeds limit")
        self._parts[chunk.index] = data
        return len(self._parts) == self.total

    def build(self) -> bytes:
        if len(self._parts) != self.total:
            raise ValueError("screenshot transfer incomplete")
        data = b"".join(self._parts[i] for i in range(self.total))
        if len(data) > MAX_FRAME_BYTES:
            raise ValueError("reassembled screenshot exceeds limit")
        digest = hashlib.sha256(data).hexdigest()
        if not hmac_equal(digest, self.expected_sha256):
            raise ValueError("screenshot digest mismatch")
        return data


def hmac_equal(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)
