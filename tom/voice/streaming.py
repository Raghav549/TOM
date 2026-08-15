from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioChunk:
    sequence: int
    pcm_or_wav: bytes
    is_final: bool = False


class StreamingVoiceSession:
    """Small transport-neutral streaming layer for Android/WebSocket clients."""

    def __init__(self, synthesizer: Callable[[str], bytes], chunk_size: int = 8192) -> None:
        self._synthesizer = synthesizer
        self._chunk_size = max(1024, chunk_size)
        self._cancelled = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    async def synthesize(self, text: str) -> AsyncIterator[AudioChunk]:
        data = await asyncio.to_thread(self._synthesizer, text)
        for sequence, start in enumerate(range(0, len(data), self._chunk_size)):
            if self._cancelled.is_set():
                return
            end = min(start + self._chunk_size, len(data))
            yield AudioChunk(sequence, data[start:end], end == len(data))
