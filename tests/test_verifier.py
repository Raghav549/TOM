from tom.models import ToolResult
from tom.verifier import ExecutionVerifier


def test_verifier_rejects_false_success_without_output() -> None:
    result = ToolResult(tool="demo", success=True, output=None)
    check = ExecutionVerifier().verify(result)
    assert check.ok is False


def test_verifier_accepts_successful_result() -> None:
    result = ToolResult(tool="demo", success=True, output={"sent": True})
    check = ExecutionVerifier().verify(result)
    assert check.ok is True


def test_expected_output_is_verified() -> None:
    verifier = ExecutionVerifier()
    result = ToolResult(tool="demo", success=True, output={"sent": True})
    assert verifier.verify_expected(result, {"sent": True}).ok is True
    assert verifier.verify_expected(result, {"sent": False}).ok is False
