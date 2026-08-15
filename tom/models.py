from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Risk(str, Enum):
    READ = "read"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: Risk = Risk.READ


class Plan(BaseModel):
    goal: str
    steps: list[ToolCall] = Field(default_factory=list)
    explanation: str = ""


class ToolResult(BaseModel):
    tool: str
    success: bool
    output: Any = None
    error: str | None = None


class AgentRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    dry_run: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    conversation_id: str
    reply: str
    plan: Plan | None = None
    pending_approval: list[ToolCall] = Field(default_factory=list)
    results: list[ToolResult] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
