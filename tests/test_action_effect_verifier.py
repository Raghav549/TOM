from tom.action_effect_verifier import ActionEffectVerifier


def test_open_app_requires_foreground_package() -> None:
    verifier = ActionEffectVerifier()
    ok = verifier.verify(action_kind="open_app", expected={"package": "com.whatsapp"}, observation={"package": "com.whatsapp", "tree": {"text": "WhatsApp"}})
    bad = verifier.verify(action_kind="open_app", expected={"package": "com.whatsapp"}, observation={"package": "com.google.android.gm"})
    assert ok.verified
    assert not bad.verified


def test_tap_requires_grounded_target_or_post_state() -> None:
    verifier = ActionEffectVerifier()
    ok = verifier.verify(action_kind="tap", expected={"target": "Send", "post_state": "sent"}, observation={"visible_text": ["Send"], "ui_state": "sent"})
    bad = verifier.verify(action_kind="tap", expected={"target": "Send", "post_state": "sent"}, observation={"visible_text": ["Home"], "ui_state": "home"})
    assert ok.verified
    assert not bad.verified


def test_search_requires_result_state_and_query() -> None:
    verifier = ActionEffectVerifier()
    ok = verifier.verify(action_kind="search", expected={"query": "cheap flights", "result_state": "loaded", "result_contains": ["Goa"]}, observation={"search_query": "cheap flights", "result_state": "loaded", "visible_text": ["Search results", "Goa"]})
    bad = verifier.verify(action_kind="search", expected={"query": "cheap flights", "result_state": "loaded"}, observation={"search_query": "cheap flights", "result_state": "error"})
    assert ok.verified
    assert not bad.verified


def test_upi_pending_is_not_success() -> None:
    verifier = ActionEffectVerifier()
    pending = verifier.verify(action_kind="upi", expected={"success_states": ["success", "completed"]}, observation={"provider_status": "pending", "transaction_id": "tx-1"})
    success = verifier.verify(action_kind="upi", expected={"success_states": ["success", "completed"]}, observation={"provider_status": "completed", "transaction_id": "tx-1"})
    assert not pending.verified
    assert success.verified
