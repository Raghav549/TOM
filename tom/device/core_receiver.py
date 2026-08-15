from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tom.perception.pipeline import MultimodalRuntime


@dataclass
class PendingObservation:
    payload: dict
    image: bytes | None = None


class CoreBridgeReceiver:
    """Core-side receiver for Android UI observations and screenshot chunks."""

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
                request_id = str(payload.get("request_id", payload.get("transfer_id", "")))
                pending = self.pending.get(request_id)
                if pending is None and len(self.pending) == 1:
                    # Safe compatibility path for older Android clients that did
                    # not echo request_id. Never guess when multiple observations
                    # are concurrently waiting for screenshots.
                    pending_id, pending = next(iter(self.pending.items()))
                    request_id = pending_id
                if pending:
                    pending.image = image
                    return await self._run(self.pending.pop(request_id))
            return None
        if message_type == "observation":
            snapshot = payload.get("snapshot") or payload.get("observation") or payload
            observation_id = str(payload.get("observation_id") or snapshot.get("observation_id") or payload.get("request_id") or snapshot.get("timestamp_ms") or "")
            if not observation_id:
                raise ValueError("observation_id required")
            from tom.perception.multimodal_observation import MultimodalObservation, UiNode
            nodes: list[UiNode] = []
            self._flatten_android_tree(snapshot.get("tree"), nodes, "root")
            for node in snapshot.get("nodes", []):
                if node.get("node_id"):
                    nodes.append(UiNode(
                        node_id=str(node["node_id"]), class_name=node.get("class_name"), text=node.get("text"),
                        content_description=node.get("content_description"),
                        bounds=tuple(node["bounds"]) if node.get("bounds") else None,
                        clickable=bool(node.get("clickable")), editable=bool(node.get("editable")),
                        enabled=bool(node.get("enabled", True)), password=bool(node.get("password")),
                    ))
            mm = MultimodalObservation(
                observation_id=observation_id,
                captured_at=str(snapshot.get("captured_at") or snapshot.get("timestamp_ms") or ""),
                package_name=snapshot.get("package") or snapshot.get("package_name"),
                window_id=snapshot.get("window_id"), nodes=tuple(nodes), frame=None,
            )
            self.pending[observation_id] = PendingObservation({"observation": mm, "intent": str(payload.get("intent") or snapshot.get("intent") or "")})
            return None
        return None

    def _flatten_android_tree(self, tree: dict | None, output: list, path: str) -> None:
        if not isinstance(tree, dict):
            return
        from tom.perception.multimodal_observation import UiNode
        bounds = tree.get("bounds")
        parsed = tuple(bounds) if isinstance(bounds, list) and len(bounds) == 4 else None
        output.append(UiNode(
            node_id=str(tree.get("node_id") or tree.get("view_id") or path),
            class_name=tree.get("class"), text=tree.get("text"), content_description=tree.get("description"),
            bounds=parsed, clickable=bool(tree.get("clickable")), editable=bool(tree.get("editable")),
            enabled=bool(tree.get("enabled", True)), password=tree.get("text") == "[REDACTED]",
        ))
        for index, child in enumerate(tree.get("children") or []):
            self._flatten_android_tree(child, output, f"{path}.{index}")

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
