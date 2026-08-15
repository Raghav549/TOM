from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Awaitable, Callable

from tom.perception.pipeline import MultimodalRuntime


@dataclass
class PendingObservation:
    payload: dict
    image: bytes | None = None


class CoreBridgeReceiver:
    """Framework-neutral Core receiver. WebSocket adapters call receive()."""

    def __init__(self, perception: MultimodalRuntime, on_plan: Callable[[dict, object], Awaitable[None]] | None = None) -> None:
        self.perception = perception
        self.on_plan = on_plan
        self.pending: dict[str, PendingObservation] = {}

    async def receive(self, message: str) -> dict | None:
        envelope = json.loads(message)
        message_type = envelope.get("type")
        payload = envelope.get("payload") or envelope
        if message_type == "screenshot_chunk":
            image = self.perception.accept_screenshot_chunk(payload)
            if image is not None:
                observation_id = str(payload.get("observation_id", payload.get("transfer_id", "")))
                pending = self.pending.get(observation_id)
                if pending:
                    pending.image = image
                    return await self._run(pending)
            return None
        if message_type == "observation":
            observation_id = str(payload.get("observation_id", ""))
            if not observation_id:
                raise ValueError("observation_id required")
            observation = payload.get("observation") or payload
            from tom.perception.multimodal_observation import MultimodalObservation, UiNode, ScreenFrame
            nodes = tuple(UiNode(
                node_id=str(node["node_id"]),
                class_name=node.get("class_name"),
                text=node.get("text"),
                content_description=node.get("content_description"),
                bounds=tuple(node["bounds"]) if node.get("bounds") else None,
                clickable=bool(node.get("clickable")),
                editable=bool(node.get("editable")),
                enabled=bool(node.get("enabled", True)),
                password=bool(node.get("password")),
            ) for node in observation.get("nodes", []))
            frame_payload = observation.get("frame")
            frame = ScreenFrame(**frame_payload) if frame_payload else None
            mm = MultimodalObservation(
                observation_id=observation_id,
                captured_at=str(observation.get("captured_at", "")),
                package_name=observation.get("package_name"),
                window_id=observation.get("window_id"),
                nodes=nodes,
                frame=frame,
            )
            self.pending[observation_id] = PendingObservation({"observation": mm, "intent": str(payload.get("intent", ""))})
            if frame_payload and frame_payload.get("inline_base64"):
                import base64
                self.pending[observation_id].image = base64.b64decode(frame_payload["inline_base64"], validate=True)
                return await self._run(self.pending.pop(observation_id))
            return None
        return None

    async def _run(self, pending: PendingObservation) -> dict:
        observation = pending.payload["observation"]
        intent = pending.payload["intent"]
        if not pending.image:
            raise ValueError("screenshot required for multimodal decision")
        decision = await self.perception.decide(observation, pending.image, intent)
        result = {
            "observation_id": decision.observation_id,
            "visual_model": decision.visual.model,
            "regions": [region.__dict__ for region in decision.visual.regions],
            "plan": decision.plan.__dict__ if decision.plan else None,
        }
        if self.on_plan:
            await self.on_plan(result, decision.plan)
        return result
