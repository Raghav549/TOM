from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ToolResult


@dataclass(frozen=True)
class Verification:
    ok: bool
    reason: str


class ExecutionVerifier:
    """Checks tool results before TOM claims that an action completed."""

    def verify(self, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(False, result.error or "tool execution failed")
        if result.output is None:
            return Verification(False, "tool reported success without an output")
        return Verification(True, "tool returned a successful result")

    def verify_expected(self, result: ToolResult, expected: dict[str, Any] | None) -> Verification:
        base = self.verify(result)
        if not base.ok or not expected:
            return base
        if not isinstance(result.output, dict):
            return Verification(False, "expected structured tool output")
        missing = [key for key, value in expected.items() if result.output.get(key) != value]
        if missing:
            return Verification(False, f"verification mismatch: {', '.join(missing)}")
        return Verification(True, "expected output verified")
