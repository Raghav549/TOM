from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .action_policy import ActionPolicy


ToolHandler = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    risk_action: str
    requires_device: bool = False
    visible_action: bool = False
    tags: tuple[str, ...] = ()


@dataclass
class ToolRegistry:
    """Single executable tool registry. A tool is registered only when it has a real handler."""

    policy: ActionPolicy = field(default_factory=ActionPolicy)
    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, tool: ToolSpec) -> None:
        if not tool.name.strip():
            raise ValueError("tool name cannot be empty")
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def replace(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise LookupError(f"unknown tool: {name}") from exc

    def list(self, *, tags: set[str] | None = None) -> list[ToolSpec]:
        tools = list(self._tools.values())
        if tags:
            tools = [tool for tool in tools if tags.intersection(tool.tags)]
        return sorted(tools, key=lambda item: item.name)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "risk_action": tool.risk_action,
                "requires_device": tool.requires_device,
                "visible_action": tool.visible_action,
                "tags": list(tool.tags),
            }
            for tool in self.list()
        ]

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        confirmed: bool = False,
    ) -> Mapping[str, Any]:
        tool = self.get(name)
        decision = self.policy.decide(tool.risk_action, explicit_confirmation=confirmed)
        if not decision.allowed:
            return {
                "ok": False,
                "tool": name,
                "error": decision.reason,
                "confirmation_required": decision.confirmation_required,
            }
        result = await tool.handler(arguments)
        return {"ok": True, "tool": name, "result": dict(result)}
