from tom.qwen_ui_policy import PerceptionMode, QwenUIPolicy


def test_uncertain_dense_ui_routes_to_fused_visual_refinement():
    decision = QwenUIPolicy().decide(
        node_count=120,
        has_screenshot=True,
        target_confidence=0.61,
        action_risk="low",
    )
    assert decision.mode is PerceptionMode.FUSED
    assert decision.require_visual_refinement is True
    assert decision.allow_batch is True


def test_consequential_action_is_never_batched():
    decision = QwenUIPolicy().decide(
        node_count=10,
        has_screenshot=True,
        target_confidence=0.99,
        action_risk="critical",
    )
    assert decision.allow_batch is False
    assert decision.require_fresh_observation is True


def test_changed_screen_discards_stale_grounding():
    decision = QwenUIPolicy().decide(
        node_count=10,
        has_screenshot=True,
        target_confidence=0.99,
        action_risk="low",
        screen_changed=True,
    )
    assert decision.require_visual_refinement is True
    assert "stale" in decision.reason


def test_visual_regions_are_clipped_by_validation_not_guesswork():
    safe = QwenUIPolicy.sanitize_visual_regions(
        [
            {"label": "Send", "confidence": 0.95, "bounds": [10, 20, 100, 70]},
            {"label": "outside", "confidence": 0.99, "bounds": [-1, 2, 20, 30]},
            {"label": "bad", "confidence": 1.5, "bounds": [0, 0, 10, 10]},
        ],
        width=200,
        height=100,
    )
    assert [item["label"] for item in safe] == ["Send"]
