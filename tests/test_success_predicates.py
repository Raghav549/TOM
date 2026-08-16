from tom.success_predicates import SuccessPredicateEngine, VerificationState


ENGINE = SuccessPredicateEngine()


def test_open_app_requires_expected_package():
    result = ENGINE.verify(
        {"kind": "open_app", "success_predicate": {"package": "com.example.app"}},
        {"foreground_package": "com.example.app", "screen": "home"},
    )
    assert result.state is VerificationState.VERIFIED


def test_open_app_wrong_package_fails():
    result = ENGINE.verify(
        {"kind": "open_app", "success_predicate": {"package": "com.example.app"}},
        {"foreground_package": "com.other.app"},
    )
    assert result.state is VerificationState.FAILED


def test_tap_requires_expected_post_state():
    result = ENGINE.verify(
        {"kind": "tap", "success_predicate": {"post_state": "settings"}},
        {"screen_changed": True, "ui_state": "settings"},
    )
    assert result.state is VerificationState.VERIFIED


def test_tap_screen_change_alone_is_not_success():
    result = ENGINE.verify(
        {"kind": "tap", "success_predicate": {"post_state": "settings"}},
        {"screen_changed": True, "ui_state": "home"},
    )
    assert result.state is VerificationState.FAILED


def test_search_requires_query_and_loaded_results():
    result = ENGINE.verify(
        {
            "kind": "search",
            "success_predicate": {
                "query": "Tesla",
                "result_state": "loaded",
                "result_contains": "Tesla",
            },
        },
        {
            "search_query": "Tesla",
            "result_state": "loaded",
            "result_text": ["Tesla Model 3", "Tesla Model Y"],
        },
    )
    assert result.state is VerificationState.VERIFIED


def test_payment_ui_success_without_authoritative_evidence_is_unknown():
    result = ENGINE.verify(
        {"kind": "upi", "success_predicate": {}},
        {
            "provider_payment_state": "success",
            "visible_text": ["Payment successful"],
            "evidence": [
                {"kind": "ocr", "value": "success", "confidence": 0.98, "authoritative": False}
            ],
        },
    )
    assert result.state is VerificationState.UNKNOWN


def test_payment_requires_authoritative_success_evidence():
    result = ENGINE.verify(
        {"kind": "upi", "success_predicate": {}},
        {
            "provider_payment_state": "success",
            "evidence": [
                {
                    "kind": "provider_callback",
                    "value": "success",
                    "confidence": 0.99,
                    "authoritative": True,
                    "source": "merchant_provider",
                }
            ],
        },
    )
    assert result.state is VerificationState.VERIFIED
