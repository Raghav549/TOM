from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import Risk, ToolCall


class Tool(Protocol):
    name: str
    risk: Risk
    description: str

    async def run(self, arguments: dict[str, Any]) -> Any: ...


@dataclass
class ToolRegistry:
    tools: dict[str, Tool]

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self.tools[tool.name] = tool

    def get(self, call: ToolCall) -> Tool:
        try:
            tool = self.tools[call.name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {call.name}") from exc
        if tool.risk is not call.risk:
            raise PermissionError(f"tool risk mismatch: {call.name}")
        return tool

    def describe(self) -> list[dict[str, Any]]:
        return [
            {"name": tool.name, "description": tool.description, "risk": tool.risk.value}
            for tool in self.tools.values()
        ]
