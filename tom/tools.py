from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import Risk, ToolCall


class Tool(Protocol):
    name: str
    risk: Risk
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
        return tool
