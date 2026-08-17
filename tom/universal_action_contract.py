from __future__ import annotations

"""Single contract shared by planner, verifier, Android bridge and browser agent.

The contract deliberately distinguishes transport acceptance from semantic success.
Unsupported/protected surfaces become explicit capability states; TOM never claims
success merely because a click/intent was accepted.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ActionType(StrEnum):
    OPEN_APP = "open_app"
    OPEN_URL = "open_url"
    TAP = "tap"
    TYPE = "type"
    SEARCH = "search"
    SCROLL = "scroll"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    SELECT = "select"
    LOGIN = "login"
    FORM_SUBMIT = "form_submit"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    SEND_MESSAGE = "send_message"
    CALL = "call"
    VIDEO_CALL = "video_call"
    UPI = "upi"
    PAYMENT = "payment"
    BOOK = "book"
    DELETE = "delete"
    PUBLISH = "publish"
    CREATE_CALENDAR_EVENT = "create_calendar_event"


class Capability(StrEnum):
    ACCESSIBILITY = "accessibility"
    SCREEN_CAPTURE = "screen_capture"
    NOTIFICATION_ACCESS = "notification_access"
    MICROPHONE = "microphone"
    CAMERA = "camera"
    PHONE = "phone"
    BROWSER = "browser"
    INTERNET = "internet"
    CREDENTIALS = "credentials"


class SurfaceState(StrEnum):
    AVAILABLE = "available"
    NEEDS_PERMISSION = "needs_permission"
    BLOCKED = "blocked"
    PROTECTED = "protected"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SuccessPredicate:
    kind: str
    expected: dict[str, Any]
    timeout_ms: int = 7000
    stability_window_ms: int = 450


@dataclass(frozen=True)
class UniversalAction:
    action_id: str
    task_id: str
    type: ActionType
    arguments: dict[str, Any]
    predicate: SuccessPredicate
    required_capabilities: tuple[Capability, ...] = ()
    irreversible: bool = False
    approval_required: bool = False


PREDICATES: dict[ActionType, str] = {
    ActionType.OPEN_APP: "open_app.expected_package_activity",
    ActionType.OPEN_URL: "browser.expected_url_page_state",
    ActionType.TAP: "tap.expected_target_state",
    ActionType.TYPE: "type.expected_field_value",
    ActionType.SEARCH: "search.expected_result_state",
    ActionType.SCROLL: "scroll.expected_anchor_visible",
    ActionType.SWIPE: "swipe.expected_state_transition",
    ActionType.LONG_PRESS: "long_press.expected_post_state",
    ActionType.SELECT: "select.expected_selection",
    ActionType.LOGIN: "login.authenticated_state",
    ActionType.FORM_SUBMIT: "form.expected_success_or_error_state",
    ActionType.UPLOAD: "upload.file_state",
    ActionType.DOWNLOAD: "download.file_state",
    ActionType.SEND_MESSAGE: "message.recipient_body_sent_evidence",
    ActionType.CALL: "call.contact_and_connected_state",
    ActionType.VIDEO_CALL: "video_call.connected_camera_audio_state",
    ActionType.UPI: "upi.provider_amount_recipient_success_evidence",
    ActionType.PAYMENT: "payment.provider_amount_recipient_success_evidence",
    ActionType.BOOK: "booking.provider_confirmation_evidence",
    ActionType.DELETE: "delete.target_absent_or_confirmation_state",
    ActionType.PUBLISH: "publish.provider_or_published_state",
    ActionType.CREATE_CALENDAR_EVENT: "calendar.provider_event_id_or_visible_event",
}


IRREVERSIBLE = {
    ActionType.SEND_MESSAGE, ActionType.CALL, ActionType.VIDEO_CALL,
    ActionType.UPI, ActionType.PAYMENT, ActionType.BOOK, ActionType.DELETE,
    ActionType.PUBLISH, ActionType.CREATE_CALENDAR_EVENT,
}


def build_action(action_id: str, task_id: str, action_type: ActionType, arguments: dict[str, Any], *, required_capabilities: tuple[Capability, ...] = ()) -> UniversalAction:
    expected = dict(arguments.get("success_predicate") or arguments.get("expected") or {})
    if action_type is ActionType.OPEN_APP:
        expected.setdefault("package", arguments.get("expected_package", arguments.get("package_name")))
        if arguments.get("expected_activity"):
            expected.setdefault("activity", arguments["expected_activity"])
    elif action_type is ActionType.TAP:
        expected.setdefault("target", arguments.get("expected_target", arguments.get("target_text")))
        if arguments.get("post_state"):
            expected.setdefault("post_state", arguments["post_state"])
    elif action_type is ActionType.TYPE:
        expected.setdefault("value", arguments.get("text", ""))
    elif action_type is ActionType.SEARCH:
        expected.setdefault("query", arguments.get("query", ""))
        expected.setdefault("result_state", "loaded")
    elif action_type in {ActionType.CALL, ActionType.VIDEO_CALL}:
        expected.setdefault("contact", arguments.get("recipient", arguments.get("contact", "")))
        expected.setdefault("connected_state", "connected")
        if action_type is ActionType.VIDEO_CALL:
            expected.setdefault("video", True)
    elif action_type in {ActionType.UPI, ActionType.PAYMENT}:
        expected.setdefault("provider", arguments.get("provider", ""))
        expected.setdefault("amount", arguments.get("amount"))
        expected.setdefault("recipient", arguments.get("recipient", ""))
        expected.setdefault("success_state", "success")
    elif action_type is ActionType.SEND_MESSAGE:
        expected.setdefault("recipient", arguments.get("recipient", ""))
        expected.setdefault("body", arguments.get("body", arguments.get("text", "")))
        expected.setdefault("sent_state", "sent")
    predicate = SuccessPredicate(PREDICATES[action_type], expected, int(arguments.get("verification_timeout_ms", 7000)), int(arguments.get("stability_window_ms", 450)))
    irreversible = action_type in IRREVERSIBLE
    return UniversalAction(action_id, task_id, action_type, dict(arguments), predicate, required_capabilities, irreversible, irreversible)


@dataclass(frozen=True)
class CapabilityState:
    capability: Capability
    state: SurfaceState
    detail: str
    remediation: str | None = None


class CapabilityMatrix:
    """Runtime capability truth; never represents unavailable access as implicit."""

    def __init__(self) -> None:
        self._states: dict[Capability, CapabilityState] = {}

    def set(self, capability: Capability, state: SurfaceState, detail: str, remediation: str | None = None) -> None:
        self._states[capability] = CapabilityState(capability, state, detail, remediation)

    def get(self, capability: Capability) -> CapabilityState:
        return self._states.get(capability, CapabilityState(capability, SurfaceState.UNKNOWN, "Not checked yet"))

    def snapshot(self) -> list[dict[str, Any]]:
        return [{"capability": item.capability.value, "state": item.state.value, "detail": item.detail, "remediation": item.remediation} for item in self._states.values()]

    def can_execute(self, action: UniversalAction) -> tuple[bool, list[CapabilityState]]:
        missing: list[CapabilityState] = []
        for capability in action.required_capabilities:
            state = self.get(capability)
            if state.state is not SurfaceState.AVAILABLE:
                missing.append(state)
        return not missing, missing
