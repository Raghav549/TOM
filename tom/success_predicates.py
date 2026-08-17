from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class VerificationState(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ActionKind(str, Enum):
    OPEN_APP = "open_app"
    OPEN_URL = "open_url"
    TAP = "tap"
    TAP_NODE = "tap_node"
    LONG_PRESS = "long_press"
    TYPE = "type"
    SEARCH = "search"
    SCROLL = "scroll"
    SWIPE = "swipe"
    BACK = "back"
    HOME = "home"
    RECENTS = "recents"
    SELECT = "select"
    FORM_SUBMIT = "form_submit"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    COMPOSE = "compose"
    SEND = "send"
    CALL = "call"
    VIDEO_CALL = "video_call"
    LOGIN = "login"
    BOOK = "book"
    DELETE = "delete"
    PUBLISH = "publish"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    PAYMENT = "payment"
    UPI = "upi"
    NOTIFICATION = "notification"
    GENERIC = "generic"


@dataclass(frozen=True)
class Evidence:
    kind: str
    value: Any
    confidence: float = 1.0
    authoritative: bool = False
    source: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    state: VerificationState
    reason: str
    confidence: float
    evidence: tuple[Evidence, ...] = ()
    observed: Mapping[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.state is VerificationState.VERIFIED


class PredicateError(ValueError):
    pass


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _contains(items: Sequence[Any] | None, expected: Any) -> bool:
    wanted = _norm(expected)
    return bool(items) and any(_norm(item) == wanted for item in items)


def _text_blob(obs: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in ("visible_text", "content_descriptions", "result_text", "notification_text", "page_text"):
        raw = obs.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            values.extend(str(x) for x in raw)
        elif raw:
            values.append(str(raw))
    return " ".join(values).casefold()


def _evidence(observation: Mapping[str, Any]) -> tuple[Evidence, ...]:
    raw = observation.get("evidence")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    result: list[Evidence] = []
    for item in raw:
        if isinstance(item, Evidence):
            result.append(item)
        elif isinstance(item, Mapping):
            try:
                confidence = float(item.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 0.0
            result.append(Evidence(str(item.get("kind", "unknown")), item.get("value"), confidence, bool(item.get("authoritative", False)), item.get("source")))
    return tuple(result)


def _fail(reason: str, obs: Mapping[str, Any], evidence: tuple[Evidence, ...] = ()) -> VerificationResult:
    return VerificationResult(VerificationState.FAILED, reason, 0.0, evidence, obs)


def _unknown(reason: str, obs: Mapping[str, Any], evidence: tuple[Evidence, ...] = ()) -> VerificationResult:
    return VerificationResult(VerificationState.UNKNOWN, reason, max((e.confidence for e in evidence), default=0.0), evidence, obs)


def _pass(reason: str, confidence: float, obs: Mapping[str, Any], evidence: tuple[Evidence, ...]) -> VerificationResult:
    return VerificationResult(VerificationState.VERIFIED, reason, max(0.0, min(1.0, confidence)), evidence, obs)


def _package(obs: Mapping[str, Any]) -> str:
    return str(obs.get("foreground_package", obs.get("package", obs.get("package_name", ""))))


class SuccessPredicateEngine:
    """Action-specific semantic verification; ACK or screen change is never success by itself."""

    DEFAULT_TIMEOUT_MS = 5000
    DEFAULT_POLL_INTERVAL_MS = 250
    DEFAULT_STABILITY_WINDOW_MS = 400

    def verify(self, action: Mapping[str, Any], observation: Mapping[str, Any] | None) -> VerificationResult:
        if observation is None:
            return _unknown("no post-action observation", {})
        raw_kind = str(action.get("kind", action.get("tool", "generic"))).lower().strip()
        try:
            kind = ActionKind(raw_kind)
        except ValueError:
            kind = ActionKind.GENERIC
        expected = action.get("success_predicate", action.get("expected", {}))
        if expected is None:
            return _unknown("action has no success predicate", observation, _evidence(observation))
        if not isinstance(expected, Mapping):
            raise PredicateError("success_predicate must be an object")
        dispatch = {
            ActionKind.OPEN_APP: self._open_app, ActionKind.OPEN_URL: self._open_url,
            ActionKind.TAP: self._tap, ActionKind.TAP_NODE: self._tap, ActionKind.LONG_PRESS: self._tap,
            ActionKind.TYPE: self._type, ActionKind.SEARCH: self._search,
            ActionKind.SCROLL: self._movement, ActionKind.SWIPE: self._movement,
            ActionKind.BACK: self._navigation, ActionKind.HOME: self._navigation, ActionKind.RECENTS: self._navigation,
            ActionKind.SELECT: self._tap, ActionKind.FORM_SUBMIT: self._submit,
            ActionKind.UPLOAD: self._file_action, ActionKind.DOWNLOAD: self._file_action,
            ActionKind.COMPOSE: self._compose, ActionKind.SEND: self._send,
            ActionKind.CALL: self._call, ActionKind.VIDEO_CALL: self._call,
            ActionKind.LOGIN: self._login, ActionKind.BOOK: self._book,
            ActionKind.DELETE: self._delete, ActionKind.PUBLISH: self._publish,
            ActionKind.CREATE_CALENDAR_EVENT: self._calendar,
            ActionKind.PAYMENT: self._payment, ActionKind.UPI: self._payment,
            ActionKind.NOTIFICATION: self._notification, ActionKind.GENERIC: self._generic,
        }
        return dispatch[kind](expected, observation)

    def _open_app(self, e, o):
        ev=_evidence(o); wanted=e.get("foreground_package",e.get("package"))
        if not wanted: return _unknown("open_app requires expected package",o,ev)
        if _norm(_package(o)) != _norm(wanted): return _fail("expected foreground package was not observed",o,ev)
        activity=e.get("activity")
        if activity and _norm(o.get("foreground_activity",o.get("activity"))) != _norm(activity): return _fail("expected foreground activity was not observed",o,ev)
        anchor=e.get("ui_anchor")
        if anchor and not (_contains(o.get("visible_text"),anchor) or _contains(o.get("content_descriptions"),anchor) or _contains(o.get("resource_ids"),anchor)): return _unknown("app is foreground but UI anchor is not confirmed",o,ev)
        return _pass("expected app is foreground",.99 if not anchor else .96,o,ev)

    def _open_url(self,e,o):
        ev=_evidence(o); url=str(o.get("url","")); host=str(e.get("host","")).strip()
        if host and host.casefold() not in url.casefold(): return _fail("expected URL host was not observed",o,ev)
        if e.get("url") and _norm(e["url"]) not in _norm(url): return _fail("expected URL was not observed",o,ev)
        state=_norm(o.get("page_state",o.get("load_state","")))
        if e.get("loaded",True) and state not in {"loaded","interactive","complete",""}: return _unknown("page is not ready",o,ev)
        return _pass("expected URL/page confirmed",.94,o,ev)

    def _tap(self,e,o):
        ev=_evidence(o); blob=_text_blob(o)
        for failure in e.get("failure_conditions",[]) if isinstance(e.get("failure_conditions",[]),Sequence) else []:
            if _norm(failure) in blob: return _fail(f"failure condition observed: {failure}",o,ev)
        target=e.get("target",e.get("expected_text")); target_present=bool(target and (_contains(o.get("visible_text"),target) or _contains(o.get("content_descriptions"),target) or _contains(o.get("resource_ids"),target) or _contains(o.get("node_ids"),target)))
        state=e.get("post_state",e.get("state")); state_match=bool(state and (_norm(o.get("screen"))==_norm(state) or _norm(o.get("ui_state"))==_norm(state) or _norm(o.get("result_state"))==_norm(state)))
        pkg=e.get("expected_package"); pkg_match=bool(pkg and _norm(_package(o))==_norm(pkg))
        if target_present and (not pkg or pkg_match) and (not state or state_match): return _pass("tap target and expected state confirmed",.98,o,ev)
        if state_match or (target_present and pkg_match): return _pass("tap postcondition confirmed",.90,o,ev)
        if e.get("allow_screen_change_only") and o.get("screen_changed") is True: return _pass("explicit screen-change predicate confirmed",.55,o,ev)
        return _fail("tap ran but expected target/state was not confirmed",o,ev)

    def _type(self,e,o):
        ev=_evidence(o); wanted=str(e.get("value",e.get("text",""))); actual=str(o.get("input_value",o.get("focused_input_value","")))
        if actual==wanted: return _pass("typed value confirmed",.98,o,ev)
        if wanted and wanted.casefold() in _text_blob(o): return _pass("typed value visible in observed UI",.86,o,ev)
        return _fail("expected typed value is not present",o,ev)

    def _search(self,e,o):
        ev=_evidence(o); q=str(e.get("query","")).strip(); actual=str(o.get("search_query",o.get("input_value",""))).strip(); state=_norm(o.get("result_state",o.get("search_state","")))
        if q and _norm(q)!=_norm(actual): return _fail("search query evidence mismatch",o,ev)
        if state in {"error","network_error","blocked","no_permission"}: return _fail(f"search ended in {state}",o,ev)
        if state!=_norm(e.get("result_state","loaded")): return _unknown("search result state is not confirmed",o,ev)
        terms=e.get("result_contains",[]); terms=[terms] if isinstance(terms,str) else terms
        if terms and not all(_norm(t) in _text_blob(o) for t in terms): return _fail("expected result anchors are missing",o,ev)
        return _pass("search query and result state confirmed",.94,o,ev)

    def _movement(self,e,o):
        ev=_evidence(o)
        if e.get("expected_scroll_position") is not None and o.get("scroll_position")==e["expected_scroll_position"]: return _pass("expected scroll position confirmed",.92,o,ev)
        if e.get("expected_anchor") and _norm(e["expected_anchor"]) in _text_blob(o): return _pass("expected post-movement anchor confirmed",.90,o,ev)
        if e.get("before_fingerprint") and o.get("fingerprint") and e["before_fingerprint"]!=o["fingerprint"]: return _pass("movement produced expected state transition",.78,o,ev)
        return _unknown("movement completed but no grounded postcondition was supplied",o,ev)

    def _navigation(self,e,o):
        ev=_evidence(o); pkg=e.get("expected_package"); screen=e.get("expected_screen",e.get("post_state"))
        if pkg and _norm(_package(o))!=_norm(pkg): return _fail("navigation target package mismatch",o,ev)
        if screen and _norm(o.get("screen",o.get("ui_state")))!=_norm(screen): return _fail("navigation target screen mismatch",o,ev)
        if pkg or screen: return _pass("navigation postcondition confirmed",.94,o,ev)
        if o.get("navigation_event") in {"home","back","recents"}: return _pass("system navigation event confirmed",.86,o,ev)
        return _unknown("navigation has no action-specific postcondition",o,ev)

    def _submit(self,e,o):
        ev=_evidence(o)
        if _norm(o.get("form_state")) in {"submitted","success","complete"}: return _pass("form submission state confirmed",.96,o,ev)
        if e.get("success_text") and _norm(e["success_text"]) in _text_blob(o): return _pass("form success message confirmed",.94,o,ev)
        if o.get("validation_errors"): return _fail("form still contains validation errors",o,ev)
        return _unknown("form submission has no positive success evidence",o,ev)

    def _file_action(self,e,o):
        ev=_evidence(o); state=_norm(o.get("file_state",o.get("upload_state",o.get("download_state",""))))
        if state in {"uploaded","downloaded","complete","completed","success"}:
            name=e.get("filename"); actual=str(o.get("filename",o.get("file_name","")))
            if name and _norm(name) not in _norm(actual): return _fail("expected filename not confirmed",o,ev)
            return _pass("file operation confirmed",.95,o,ev)
        if state in {"failed","error","cancelled","canceled"}: return _fail(f"file operation ended in {state}",o,ev)
        return _unknown("file operation is not yet confirmed",o,ev)

    def _compose(self,e,o):
        ev=_evidence(o); blob=_text_blob(o); recipient=str(e.get("recipient","")).strip(); body=str(e.get("body",e.get("text",""))).strip()
        if recipient and recipient.casefold() not in blob: return _fail("recipient is not visible in composer",o,ev)
        if body and body[:120].casefold() not in blob: return _fail("message body is not visible in composer",o,ev)
        return _pass("composer contains requested payload",.95,o,ev)

    def _send(self,e,o):
        ev=_evidence(o); state=_norm(o.get("provider_status",o.get("send_state",o.get("message_state","")))); blob=_text_blob(o)
        if state in {"failed","error","rejected","cancelled","canceled"}: return _fail(f"send provider reports {state}",o,ev)
        recipient=str(e.get("recipient","")).strip(); body=str(e.get("body",e.get("text",""))).strip()
        recipient_ok=not recipient or recipient.casefold() in blob or _norm(o.get("recipient",o.get("sent_to","")))==_norm(recipient)
        body_ok=not body or body[:120].casefold() in blob or _norm(o.get("message_body",o.get("sent_body","")))==_norm(body)
        authoritative=[x for x in ev if x.authoritative and x.confidence>=.90]
        if any(_norm(x.value) in {"sent","delivered","submitted","success","completed"} for x in authoritative) and recipient_ok and body_ok: return _pass("send confirmed by authoritative evidence",.995,o,tuple(authoritative))
        if state in {"sent","delivered","submitted","success","completed"} and recipient_ok and body_ok: return _pass("send provider state and payload confirmed",.97,o,ev)
        if any(x in blob for x in ("message sent","email sent","sms sent","delivered")) and recipient_ok and body_ok: return _pass("positive send confirmation and payload observed",.94,o,ev)
        return _unknown("no trustworthy send success evidence with payload confirmation",o,ev)

    def _call(self,e,o):
        ev=_evidence(o); state=_norm(o.get("call_state",o.get("telephony_state",o.get("video_call_state",""))))
        if state in {"failed","busy","rejected","ended","disconnected","error"}: return _fail(f"call state is {state}",o,ev)
        contact=str(e.get("contact",e.get("recipient",""))).strip(); actual=str(o.get("contact",o.get("connected_contact",o.get("phone_number","")))).strip()
        if contact and actual and _norm(contact)!=_norm(actual): return _fail("connected contact does not match requested contact",o,ev)
        if state in {"connected","active","in_call","ongoing","offhook"}:
            if e.get("video") is True and not o.get("camera_active",o.get("video_active",False)): return _unknown("video call connected but camera state is not confirmed",o,ev)
            if e.get("audio",True) and not o.get("audio_active",o.get("microphone_active",True)): return _unknown("call connected but audio state is not confirmed",o,ev)
            return _pass("call connection and requested media state confirmed",.97,o,ev)
        return _unknown("call is not yet confirmed connected",o,ev)

    def _login(self,e,o):
        ev=_evidence(o); state=_norm(o.get("authentication_state",o.get("auth_state","")))
        if state in {"authenticated","logged_in","signed_in"}: return _pass("authenticated state confirmed",.995,o,ev)
        if state in {"failed","invalid_credentials","locked","blocked"}: return _fail(f"authentication state is {state}",o,ev)
        return _unknown("authenticated state not confirmed",o,ev)

    def _book(self,e,o):
        ev=_evidence(o); state=_norm(o.get("booking_state",o.get("provider_status",""))); confirmation=str(o.get("booking_confirmation",o.get("confirmation_id",""))).strip()
        if state in {"failed","cancelled","canceled","error","rejected"}: return _fail(f"booking state is {state}",o,ev)
        if state in {"confirmed","booked","success","completed"} and confirmation: return _pass("booking state and confirmation evidence confirmed",.999,o,ev)
        return _unknown("booking confirmation is not yet authoritative",o,ev)

    def _delete(self,e,o):
        ev=_evidence(o)
        if o.get("target_absent") is True: return _pass("target absent after deletion",.99,o,ev)
        state=_norm(o.get("operation_state",o.get("delete_state","")))
        if state in {"failed","error","rejected"}: return _fail(f"delete state is {state}",o,ev)
        if state in {"deleted","success","completed"} and o.get("deleted_target"): return _pass("deletion state and target evidence confirmed",.98,o,ev)
        return _unknown("deletion has no positive postcondition",o,ev)

    def _publish(self,e,o):
        ev=_evidence(o); state=_norm(o.get("publish_state",o.get("provider_status","")))
        if state in {"failed","rejected","blocked","error"}: return _fail(f"publish state is {state}",o,ev)
        if state in {"published","live","success","completed"} and (o.get("published_id") or o.get("published_url") or "published" in _text_blob(o)): return _pass("published state and provider/UI evidence confirmed",.995,o,ev)
        return _unknown("publish success evidence not confirmed",o,ev)

    def _calendar(self,e,o):
        ev=_evidence(o); event_id=str(o.get("event_id",o.get("provider_event_id",""))); title=str(e.get("title",""))
        if event_id: return _pass("calendar provider returned event identifier",.995,o,ev)
        if title and title.casefold() in _text_blob(o) and _norm(o.get("calendar_state")) in {"created","visible","success","confirmed","saved"}: return _pass("calendar event is visible",.92,o,ev)
        return _unknown("calendar creation is not confirmed",o,ev)

    def _payment(self,e,o):
        ev=_evidence(o); state=_norm(o.get("provider_payment_state",o.get("payment_state",o.get("provider_status","")))); txn=o.get("transaction_id",o.get("txn_id",o.get("utr")))
        if state in {"failed","cancelled","canceled","declined","error","reversed"}: return _fail(f"payment provider reports {state}",o,ev)
        if state in {"pending","processing","requires_action","authorization_required"}: return _unknown(f"payment remains {state}",o,ev)
        authoritative=any(x.authoritative and x.confidence>=.90 and _norm(x.value) in {"success","succeeded","completed","paid"} for x in ev)
        if state in {"success","succeeded","completed","paid"} and (authoritative or txn): return _pass("payment success has provider evidence",.999,o,ev)
        if any(x in _text_blob(o) for x in ("payment successful","payment complete","transaction successful")): return _unknown("payment UI suggests success but provider evidence is missing",o,ev)
        return _unknown("no authoritative payment success evidence",o,ev)

    def _notification(self,e,o):
        ev=_evidence(o); source=str(e.get("package",e.get("source",""))); text=str(e.get("text",e.get("contains",""))); pkg=str(o.get("notification_package",o.get("package",""))); nt=str(o.get("notification_text",""))
        if source and _norm(source)!=_norm(pkg): return _fail("notification source package mismatch",o,ev)
        if text and _norm(text) not in _norm(nt): return _fail("notification content does not match expected text",o,ev)
        if o.get("notification_id") or nt: return _pass("notification received and matched",.97 if source and text else .90,o,ev)
        return _unknown("notification has not arrived or has not been observed",o,ev)

    def _generic(self,e,o):
        ev=_evidence(o)
        for key,value in e.items():
            if key in {"timeout_ms","poll_interval_ms","stability_window_ms","failure_conditions"}: continue
            if o.get(key)!=value: return _fail(f"expected {key}={value!r}, observed {o.get(key)!r}",o,ev)
        return _pass("expected predicate fields observed",.90,o,ev)
