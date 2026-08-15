import hashlib

import pytest

from tom.perception.fusion import PerceptionFusion
from tom.perception.multimodal_observation import MultimodalObservation, UiNode
from tom.perception.screenshot_reassembler import ScreenshotReassembler
from tom.perception.screenshot_transport import ScreenshotChunker
from tom.perception.visual_adapter import VisualAnalysis, VisualRegion


def test_screenshot_chunks_reassemble_with_digest():
    data = b"screen" * 10000
    chunks = ScreenshotChunker(1024).split("t1", data)
    receiver = ScreenshotReassembler("t1", len(chunks), hashlib.sha256(data).hexdigest())
    for chunk in reversed(chunks):
        receiver.add(chunk)
    assert receiver.build() == data


def test_screenshot_digest_mismatch_fails():
    data = b"screen"
    chunks = ScreenshotChunker(1024).split("t2", data)
    receiver = ScreenshotReassembler("t2", 1, "0" * 64)
    receiver.add(chunks[0])
    with pytest.raises(ValueError, match="digest mismatch"):
        receiver.build()


def test_visual_region_fuses_with_ui_node():
    node = UiNode("0.1", text="Send", bounds=(100, 100, 220, 160), clickable=True)
    obs = MultimodalObservation.now("o1", "com.example", (node,))
    visual = VisualAnalysis("test", (VisualRegion("send button", 0.9, (105, 105, 215, 155)),))
    result = PerceptionFusion().fuse(obs.nodes, visual)
    assert result[0].node_id == "0.1"
    assert result[0].fused_score > 0.8
