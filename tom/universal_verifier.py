from __future__ import annotations

from typing import Any, Mapping


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _blob(obs: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "visible_text",
        "content_descriptions",
        "result_text",
        "notification_text",
        "page_text",
    ):
        value = obs.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return " ".join(values).casefold()


def verify_universal(
    action: str,
    expected: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> tuple[bool, float, str, tuple[str, ...]] | None:
    """Return a hard predicate for actions that need semantic proof."""
    kind = action.casefold()

    if kind in {"login", "device_login"}:
        auth = _norm(observation.get("authentication_state", observation.get("auth_state")))
        if auth in {"authenticated", "logged_in", "signed_in"}:
            return True, 0.995, "authenticated state confirmed", ("authentication_state",)
        if auth in {"failed", "invalid_credentials", "locked", "blocked"}:
            return False, 0.0, f"authentication state is {auth}", ("authentication_state",)
        return False, 0.0, "authenticated state not confirmed", ()

    if kind in {"send_message", "send_email", "send_sms", "communication.sms_send", "google.gmail_send"}:
        recipient = _norm(expected.get("recipient"))
        body = _norm(expected.get("body", expected.get("text")))
        actual_recipient = _norm(observation.get("recipient", observation.get("sent_to")))
        actual_body = _norm(observation.get("message_body", observation.get("sent_body")))
        state = _norm(observation.get("message_state", observation.get("send_state", observation.get("provider_status"))))
        if recipient and actual_recipient and recipient != actual_recipient:
            return False, 0.0, "recipient evidence mismatch", ("recipient",)
        if body and actual_body and body != actual_body:
            return False, 0.0, "message body evidence mismatch", ("message_body",)
        if state in {"sent", "delivered", "submitted", "success", "completed"} and actual_recipient and actual_body:
            return True, 0.995, "recipient, body and sent state confirmed", ("recipient", "message_body", "message_state")
        if state in {"failed", "rejected", "cancelled", "canceled", "error"}:
            return False, 0.0, f"message send state is {state}", ("message_state",)
        return False, 0.0, "recipient/body/sent evidence incomplete", ()

    if kind in {"call", "device_call"}:
        state = _norm(observation.get("call_state", observation.get("telephony_state")))
        if state in {"connected", "active", "in_call", "offhook"}:
            return True, 0.995, "telephony call state confirms active call", ("call_state",)
        if state in {"failed", "busy", "rejected", "ended", "disconnected", "error"}:
            return False, 0.0, f"call state is {state}", ("call_state",)
        return False, 0.0, "active call state not confirmed", ()

    if kind in {"video_call", "device_video_call"}:
        call_state = _norm(observation.get("call_state", observation.get("video_call_state")))
        video = bool(observation.get("video_active", observation.get("camera_active", False)))
        audio = bool(observation.get("audio_active", observation.get("microphone_active", False)))
        if call_state in {"connected", "active", "in_call", "ongoing"} and video and audio:
            return True, 0.995, "connected call with active video and audio confirmed", ("call_state", "video_active", "audio_active")
        if call_state in {"failed", "busy", "rejected", "ended", "disconnected", "error"}:
            return False, 0.0, f"video call state is {call_state}", ("call_state",)
        return False, 0.0, "video/audio active state not fully confirmed", ()

    if kind in {"book", "booking", "device_book"}:
        confirmation = str(observation.get("booking_confirmation", observation.get("confirmation_id", ""))).strip()
        state = _norm(observation.get("booking_state", observation.get("provider_status")))
        if confirmation and state in {"confirmed", "booked", "success", "completed"}:
            return True, 0.999, "provider booking confirmation evidence", ("confirmation_id", "booking_state")
        if state in {"failed", "cancelled", "canceled", "error"}:
            return False, 0.0, f"booking state is {state}", ("booking_state",)
        return False, 0.0, "booking confirmation not present", ()

    if kind in {"create_calendar_event", "device_create_calendar_event"}:
        event_id = str(observation.get("event_id", observation.get("provider_event_id", observation.get("id", "")))).strip()
        title = _norm(expected.get("title"))
        blob = _blob(observation)
        title_visible = bool(title and title in blob)
        if event_id:
            return True, 0.99, "calendar provider event id confirmed", ("event_id",)
        if title_visible and _norm(observation.get("calendar_state")) in {"created", "confirmed", "saved", "success", "completed"}:
            return True, 0.98, "calendar event visible in confirmed state", ("event_title", "calendar_state")
        if _norm(observation.get("calendar_state")) in {"failed", "error", "cancelled", "canceled"}:
            return False, 0.0, "calendar event creation failed", ("calendar_state",)
        return False, 0.0, "calendar creation is not confirmed", ()

    if kind in {"delete", "device_delete"}:
        if observation.get("target_absent") is True:
            return True, 0.99, "target is absent after deletion", ("target_absent",)
        if _norm(observation.get("operation_state")) in {"deleted", "success", "completed"} and observation.get("deleted_target"):
            return True, 0.98, "deletion state and target evidence confirmed", ("operation_state", "deleted_target")
        return False, 0.0, "deletion has no positive postcondition", ()

    if kind in {"publish", "device_publish"}:
        state = _norm(observation.get("publish_state", observation.get("provider_status")))
        if state in {"published", "live", "success", "completed"} and (observation.get("published_id") or observation.get("published_url") or "published" in _blob(observation)):
            return True, 0.995, "published state and provider/UI evidence confirmed", ("publish_state",)
        if state in {"failed", "rejected", "blocked", "error"}:
            return False, 0.0, f"publish state is {state}", ("publish_state",)
        return False, 0.0, "publish success evidence not confirmed", ()

    if kind in {"upi", "upi_payment", "device_upi_payment", "payment", "device_payment"}:
        provider = _norm(observation.get("payment_provider", observation.get("provider")))
        amount = observation.get("payment_amount", observation.get("amount"))
        recipient = _norm(observation.get("payment_recipient", observation.get("recipient")))
        state = _norm(observation.get("provider_payment_state", observation.get("payment_state", observation.get("provider_status"))))
        txn = str(observation.get("transaction_id", observation.get("utr", observation.get("txn_id", "")))).strip()
        if expected.get("provider") and provider and provider != _norm(expected["provider"]):
            return False, 0.0, "payment provider mismatch", ("payment_provider",)
        if expected.get("amount") is not None and amount is not None and str(amount) != str(expected["amount"]):
            return False, 0.0, "payment amount mismatch", ("payment_amount",)
        if expected.get("recipient") and recipient and recipient != _norm(expected["recipient"]):
            return False, 0.0, "payment recipient mismatch", ("payment_recipient",)
        if state in {"success", "succeeded", "completed", "paid"} and txn:
            return True, 0.999, "provider, amount, recipient and transaction success evidence confirmed", ("payment_provider", "payment_amount", "payment_recipient", "transaction_id")
        if state in {"failed", "declined", "cancelled", "canceled", "error"}:
            return False, 0.0, f"payment state is {state}", ("payment_state",)
        return False, 0.0, "authoritative payment evidence incomplete", ()

    return None
