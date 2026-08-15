from __future__ import annotations

from dataclasses import dataclass
import hashlib
import tempfile
from pathlib import Path

from .fusion import FusedTarget, PerceptionFusion
from .multimodal_observation import MultimodalObservation
from .openai_compatible_vision import OpenAICompatibleVision
from .screenshot_reassembler import ScreenshotReassembler
from .visual_adapter import VisualModelAdapter


@dataclass
class VisionPipeline:
    adapter: VisualModelAdapter
    fusion: PerceptionFusion

    async def analyze_observation(
        self,
        observation: MultimodalObservation,
        transfer_id: str,
        total: int,
        sha256: str,
        chunks: list[dict[str, object]],
        prompt: str,
    ) -> list[FusedTarget]:
        from .screenshot_transport import ScreenshotChunk

        reassembler = ScreenshotReassembler(transfer_id, total, sha256)
        for raw in chunks:
            reassembler.add(ScreenshotChunk(
                transfer_id=str(raw["transfer_id"]),
                index=int(raw["index"]),
                total=int(raw["total"]),
                sha256=str(raw["sha256"]),
                data_b64=str(raw["data_b64"]),
            ))
        image = reassembler.build()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(image)
            path = Path(handle.name)
        try:
            analysis = await self.adapter.analyze(str(path), prompt=prompt)
            return self.fusion.fuse(observation.nodes, analysis)
        finally:
            path.unlink(missing_ok=True)
