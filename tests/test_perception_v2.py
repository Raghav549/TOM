from __future__ import annotations

from tom.perception.fusion import PerceptionFusion
from tom.perception.multimodal_observation import UiNode
from tom.perception.state_tracker import ScreenStateTracker
from tom.perception.visual_adapter import VisualAnalysis, VisualRegion


def test_state_tracker_detects_real_screen_change() -> None:
    tracker = ScreenStateTracker()
    first = {
        "package": "com.example",
        "window_id": 1,
        "nodes": [{"id": "0.0", "text": "Search", "bounds": [0, 0, 300, 100], "clickable": True}],
    }
    second = {
        "package": "com.example",
        "window_id": 1,
        "nodes": [{"id": "0.0", "text": "Results", "bounds": [0, 0, 300, 100], "clickable": True}],
    }
    _, initial = tracker.update(first)
    _, delta = tracker.update(second)
    assert initial.changed
    assert delta.changed
    assert delta.text_changed


def test_fusion_prefers_accessibility_semantics() -> None:
    nodes = (
        UiNode(
            node_id="0.1",
            text="Search flights",
            bounds=(10, 20, 300, 100),
            clickable=True,
        ),
    )
    visual = VisualAnalysis(
        model="test",
        regions=(VisualRegion("Search flights", 0.90, (8, 18, 302, 102)),),
    )
    targets = PerceptionFusion().ground("search flights", nodes, visual)
    assert targets
    assert targets[0].node_id == "0.1"
    assert "accessibility" in targets[0].evidence or "accessibility_overlap" in targets[0].evidence


def test_password_nodes_are_never_grounded() -> None:
    nodes = (
        UiNode(node_id="0.2", text="secret", bounds=(0, 0, 100, 100), clickable=True, password=True),
    )
    targets = PerceptionFusion().ground("secret", nodes)
    assert not targets
