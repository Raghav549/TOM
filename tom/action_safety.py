from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Risk, ToolCall


@dataclass(frozen=True)
class PreconditionResult:
    ok: bool
    reason: str = ""
    normalized_arguments: dict[str, Any] | None = None


class ActionPreconditionChecker:
    """Fail-closed checks before an action reaches a real device/provider."""

    REQUIRED_ARGUMENTS: dict[str, tuple[str, ...]] = {
        "device_tap_node": ("node_id",),
        "device_set_text": ("node_id", "text"),
        "device_swipe": ("x1", "y1", "x2", "y2"),
        "device_open_app": ("package_name",),
        "device_open_url": ("url",),
        "device_send_message": ("recipient", "message"),
        "device_send_email": ("recipient", "subject", "body"),
        "device_create_calendar_event": ("title", "start_time"),
        "device_upi_payment": ("pa", "pn", "am"),
    }

    CONSEQUENTIAL: frozenset[Risk] = frozenset({Risk.HIGH, Risk.CRITICAL})

    def check(self, call: ToolCall, *, observed_state: dict[str, Any] | None = None) -> PreconditionResult:
        args = dict(call.arguments)
        for key in self.REQUIRED_ARGUMENTS.get(call.name, ()):
            if key not in args or args[key] in (None, ""):
                return PreconditionResult(False, f"missing required argument: {key}")
        state = observed_state or {}
        expected_package = str(args.get("expected_package", "")).strip()
        current_package = str(state.get("package_name", "")).strip()
        if expected_package and current_package and expected_package != current_package:
            return PreconditionResult(False, "screen package changed; re-observation required")
        expected_fingerprint = str(args.get("expected_fingerprint", "")).strip()
        current_fingerprint = str(state.get("fingerprint", "")).strip()
        if expected_fingerprint and current_fingerprint and expected_fingerprint != current_fingerprint:
            return PreconditionResult(False, "screen state is stale; re-ground before acting")
        if call.risk in self.CONSEQUENTIAL and not args.get("approval_token") and not args.get("approved"):
            return PreconditionResult(False, "explicit approval token required")
        return PreconditionResult(True, normalized_arguments=args)
