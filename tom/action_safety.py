from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .models import Risk, ToolCall


@dataclass(frozen=True)
class PreconditionResult:
    ok: bool
    reason: str = ""
    normalized_arguments: dict[str, Any] | None = None


class ActionPreconditionChecker:
    """Fail-closed checks before an action reaches a real device/provider.

    A transport ACK or a changed screenshot is never treated as task success.
    Device actions that can change state must carry an explicit, grounded
    success predicate so ActionSpecificVerifier can verify the postcondition.
    """

    REQUIRED_ARGUMENTS: ClassVar[dict[str, tuple[str, ...]]] = {
        "device_tap_node": ("node_id",),
        "device_set_text": ("node_id", "text"),
        "device_swipe": ("x1", "y1", "x2", "y2"),
        "device_open_app": ("package_name",),
        "device_open_url": ("url",),
        "device_send_message": ("recipient", "message"),
        "device_send_email": ("recipient", "subject", "body"),
    }

    ALTERNATIVE_ARGUMENTS: ClassVar[dict[str, tuple[tuple[str, ...], ...]]] = {
        "device_create_calendar_event": (("title", "start_time"), ("title", "start_millis", "end_millis")),
        "device_upi_payment": (("intent_uri",), ("pa", "pn", "am")),
    }

    # These actions must prove their intended postcondition. For reversible
    # navigation we allow an explicit navigation event as the predicate.
    PREDICATE_REQUIRED: ClassVar[frozenset[str]] = frozenset({
        "device_open_app", "device_open_url", "device_tap", "device_tap_node",
        "device_set_text", "device_search_google", "device_send_message",
        "device_send_email", "device_create_calendar_event", "device_upi_payment",
        "device_call", "device_video_call", "device_form_submit", "device_upload",
        "device_download", "device_select", "device_long_press", "device_scroll",
        "device_swipe", "device_back", "device_home", "device_recents",
    })

    CONSEQUENTIAL: ClassVar[frozenset[Risk]] = frozenset({Risk.HIGH, Risk.CRITICAL})

    def check(self, call: ToolCall, *, observed_state: dict[str, Any] | None = None) -> PreconditionResult:
        args = dict(call.arguments)
        required = self.REQUIRED_ARGUMENTS.get(call.name, ())
        for key in required:
            if key not in args or args[key] in (None, ""):
                return PreconditionResult(False, f"missing required argument: {key}")

        alternatives = self.ALTERNATIVE_ARGUMENTS.get(call.name, ())
        if alternatives and not any(all(args.get(key) not in (None, "") for key in group) for group in alternatives):
            expected = " or ".join(" + ".join(group) for group in alternatives)
            return PreconditionResult(False, f"missing required arguments: {expected}")

        if call.name in self.PREDICATE_REQUIRED:
            predicate = args.get("success_predicate") or args.get("expected")
            if not isinstance(predicate, dict) or not predicate:
                return PreconditionResult(False, "grounded success_predicate required; re-ground before acting")

        state = observed_state or {}
        expected_package = str(args.get("expected_package", "")).strip()
        current_package = str(state.get("package_name", state.get("foreground_package", ""))).strip()
        if expected_package and current_package and expected_package != current_package:
            return PreconditionResult(False, "screen package changed; re-observation required")
        expected_fingerprint = str(args.get("expected_fingerprint", "")).strip()
        current_fingerprint = str(state.get("fingerprint", "")).strip()
        if expected_fingerprint and current_fingerprint and expected_fingerprint != current_fingerprint:
            return PreconditionResult(False, "screen state is stale; re-ground before acting")
        if call.risk in self.CONSEQUENTIAL and not args.get("approval_token") and not args.get("approved"):
            return PreconditionResult(False, "explicit approval token required")
        return PreconditionResult(True, normalized_arguments=args)
