from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from tom.perception.pipeline import MultimodalRuntime


@dataclass
class PendingObservation:
    payload: dict[str, Any]
    image: bytes | None = None


class CoreBridgeReceiver:
    """Reconstruct Android screenshots and bind multimodal decisions to task/action IDs."""

    def __init__(
        self,
        perception: MultimodalRuntime,
        on_plan: Callable[[dict, object], Awaitable[None]] | None = None,
        on_result: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self.perception = perception
        self.on_plan = on_plan
        self.on_result = on_result
        self.pending: dict[str, PendingObservation] = {}
        self._aliases: dict[str, str] = {}

    @staticmethod
    def _key(payload: dict[str, Any]) -> str:
        task_id = str(payload.get("task_id") or "").strip()
        action_id = str(payload.get("action_id") or "").strip()
        if task_id and action_id:
            return f"{task_id}:{action_id}"
        return str(payload.get("observation_id") or payload.get("request_id") or payload.get("transfer_id") or "")

    async def receive(self, message: str) -> dict | None:
        envelope = json.loads(message)
        message_type = envelope.get("type")
        payload = envelope.get("payload") or envelope

        if message_type == "screenshot_chunk":
            image = self.perception.accept_screenshot_chunk(payload)
            if image is None:
                return None
            key = self._aliases.get(self._key(payload), self._key(payload))
            pending = self.pending.get(key)
            if pending is None and len(self.pending) == 1:
                # Compatibility fallback for older Android clients with no task/action echo.
                key, pending = next(iter(self.pending.items()))
            if pending is None:
                return None
            pending.image = image
            result = await self._run(self.pending.pop(key))
            self._drop_aliases(key)
            return result

        if message_type == "observation":
            snapshot = payload.get("snapshot") or payload.get("observation") or payload
            observation_id = str(
                payload.get("observation_id")
                or snapshot.get("observation_id")
                or payload.get("request_id")
                or snapshot.get("timestamp_ms")
                or ""
            )
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
            key = self._key(payload) or observation_id
            self.pending[key] = PendingObservation({
                "observation": mm,
                "intent": str(payload.get("intent") or snapshot.get("intent") or ""),
                "task_id": str(payload.get("task_id") or ""),
                "action_id": str(payload.get("action_id") or ""),
                "observation_id": observation_id,
            })
            self._aliases[observation_id] = key
            request_id = str(payload.get("request_id") or "")
            if request_id:
                self._aliases[request_id] = key
            return None
        return None

    def _drop_aliases(self, key: str) -> None:
        for alias, target in list(self._aliases.items()):
            if target == key:
                self._aliases.pop(alias, None)

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
        reasons = list(decision.delta.reasons)
        # A first-ever observation has no before-state. It is useful perception,
        # but it is not proof that an action succeeded. This prevents a fresh
        # task from being marked complete merely because a screenshot exists.
        has_before_state = "initial_observation" not in reasons
        changed = bool(decision.delta.changed and has_before_state)
        result = {
            "task_id": pending.payload.get("task_id") or None,
            "action_id": pending.payload.get("action_id") or None,
            "observation_id": decision.observation_id,
            "visual_model": decision.visual.model,
            "regions": [region.__dict__ for region in decision.visual.regions],
            "plan": decision.plan.__dict__ if decision.plan else None,
            "state": decision.state.__dict__,
            "delta": decision.delta.__dict__,
            "verification": {
                "status": "verified" if changed else "unknown",
                "confidence": 1.0 if changed else 0.0,
                "evidence": reasons or ["no_verified_state_transition"],
            },
        }
        if self.on_plan:
            await self.on_plan(result, decision.plan)
        if self.on_result:
            await self.on_result(result)
        return result
