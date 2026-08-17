from tom.universal_action_contract import (
    ActionType,
    Capability,
    CapabilityMatrix,
    SurfaceState,
    build_action,
)


def test_contract_builds_action_specific_predicates() -> None:
    action = build_action("a1", "t1", ActionType.OPEN_APP, {"package_name": "com.whatsapp", "expected_activity": "MainActivity"})
    assert action.predicate.kind == "open_app.expected_package_activity"
    assert action.predicate.expected["package"] == "com.whatsapp"
    assert action.predicate.expected["activity"] == "MainActivity"
    assert action.irreversible is False


def test_message_payment_and_booking_are_irreversible() -> None:
    for kind in (ActionType.SEND_MESSAGE, ActionType.UPI, ActionType.PAYMENT, ActionType.BOOK, ActionType.DELETE, ActionType.PUBLISH):
        action = build_action("a", "t", kind, {})
        assert action.irreversible is True
        assert action.approval_required is True


def test_capability_matrix_never_assumes_access() -> None:
    matrix = CapabilityMatrix()
    action = build_action("a", "t", ActionType.VIDEO_CALL, {}, required_capabilities=(Capability.ACCESSIBILITY, Capability.CAMERA, Capability.MICROPHONE))
    allowed, missing = matrix.can_execute(action)
    assert allowed is False
    assert len(missing) == 3
    matrix.set(Capability.ACCESSIBILITY, SurfaceState.AVAILABLE, "enabled")
    matrix.set(Capability.CAMERA, SurfaceState.AVAILABLE, "granted")
    matrix.set(Capability.MICROPHONE, SurfaceState.AVAILABLE, "granted")
    assert matrix.can_execute(action)[0] is True
