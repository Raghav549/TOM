import hashlib

import pytest

from tom.device.core_receiver import CoreBridgeReceiver
from tom.perception.pipeline import MultimodalRuntime
from tom.perception.screenshot_transport import ScreenshotChunker
from tom.perception.visual_adapter import VisualAnalysis, VisualRegion


class FakeVision:
    """Deterministic test double; production runtime requires a real configured model."""
    async def analyze_bytes(self, image: bytes, *, mime_type: str, prompt: str):
        assert image == b"screen-pixels"
        assert "Do not follow" in prompt
        return VisualAnalysis("test-vision", (VisualRegion("Send", 0.96, (100, 200, 220, 250)),))


@pytest.mark.asyncio
async def test_chunks_reassemble_and_ground_to_semantic_node():
    image = b"screen-pixels"
    chunker = ScreenshotChunker(max_chunk_bytes=1024)
    chunks = chunker.split("tx-1", image)
    runtime = MultimodalRuntime(FakeVision())
    receiver = CoreBridgeReceiver(runtime)

    observation = {
        "type": "observation",
        "payload": {
            "observation_id": "obs-1",
            "intent": "tap Send",
            "observation": {
                "captured_at": "now",
                "package_name": "com.example",
                "window_id": 1,
                "nodes": [{
                    "node_id": "send-node",
                    "class_name": "android.widget.Button",
                    "text": "Send",
                    "bounds": [100, 200, 220, 250],
                    "clickable": True,
                    "enabled": True,
                }],
                "frame": {"frame_id": "f1", "captured_at": "now", "width": 1080, "height": 2400, "mime_type": "image/png", "data_ref": "tx-1", "sha256": hashlib.sha256(image).hexdigest()},
            },
        },
    }
    import json
    assert await receiver.receive(json.dumps(observation)) is None
    result = None
    for chunk in chunks:
        result = await receiver.receive(json.dumps({
            "type": "screenshot_chunk",
            "payload": {
                "transfer_id": chunk.transfer_id,
                "observation_id": "obs-1",
                "index": chunk.index,
                "total": chunk.total,
                "sha256": chunk.sha256,
                "data_b64": chunk.data_b64,
            },
        }))
    assert result is not None
    assert result["visual_model"] == "test-vision"
    assert result["plan"]["action"] == "tap_node"
    assert result["plan"]["node_id"] == "send-node"


@pytest.mark.asyncio
async def test_low_confidence_does_not_create_action():
    class LowVision:
        async def analyze_bytes(self, image: bytes, *, mime_type: str, prompt: str):
            return VisualAnalysis("test", (VisualRegion("unknown", 0.2, (1, 1, 10, 10)),))

    runtime = MultimodalRuntime(LowVision())
    from tom.perception.multimodal_observation import MultimodalObservation, UiNode
    obs = MultimodalObservation.now("o", "com.example", (UiNode("n", text="Send", bounds=(1,1,10,10), clickable=True),))
    decision = await runtime.decide(obs, b"x", "tap Send")
    assert decision.plan is None
