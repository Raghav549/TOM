from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

MAX_CHUNK_BYTES = 256 * 1024
MAX_FRAME_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class ScreenshotChunk:
    transfer_id: str
    index: int
    total: int
    sha256: str
    data_b64: str


class ScreenshotChunker:
    def __init__(self, max_chunk_bytes: int = MAX_CHUNK_BYTES) -> None:
        if not 1024 <= max_chunk_bytes <= MAX_CHUNK_BYTES:
            raise ValueError("unsafe chunk size")
        self.max_chunk_bytes = max_chunk_bytes

    def split(self, transfer_id: str, data: bytes) -> list[ScreenshotChunk]:
        if len(data) > MAX_FRAME_BYTES:
            raise ValueError("screenshot exceeds transport limit")
        total = max(1, math.ceil(len(data) / self.max_chunk_bytes))
        digest = hashlib.sha256(data).hexdigest()
        import base64
        return [
            ScreenshotChunk(
                transfer_id=transfer_id,
                index=i,
                total=total,
                sha256=digest,
                data_b64=base64.b64encode(data[i * self.max_chunk_bytes:(i + 1) * self.max_chunk_bytes]).decode("ascii"),
            )
            for i in range(total)
        ]
