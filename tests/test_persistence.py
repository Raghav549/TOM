import pytest

from tom.persistence import SupabaseTaskStore
from tom.action_predicates import VerificationContext, default_predicates


def test_persistence_requires_explicit_supabase_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOM_SUPABASE_URL", raising=False)
    monkeypatch.delenv("TOM_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError):
        SupabaseTaskStore()


def test_upi_predicate_fails_closed_without_terminal_provider_evidence() -> None:
    result = default_predicates().evaluate(
        VerificationContext(
            action="upi_payment",
            arguments={"pa": "merchant@upi", "am": "100"},
            before={},
            after={"payment_status": "success"},
        )
    )
    assert result.success is False


def test_upi_predicate_accepts_provider_success_with_transaction() -> None:
    result = default_predicates().evaluate(
        VerificationContext(
            action="upi_payment",
            arguments={"pa": "merchant@upi", "am": "100"},
            before={},
            after={"payment_status": "success", "transaction_id": "UTR-123"},
        )
    )
    assert result.success is True
