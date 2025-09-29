"""Tests for the deterministic IC matching engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from intercompany_close_agent.matching.engine import match_transactions
from intercompany_close_agent.models.exception import ExceptionType
from intercompany_close_agent.models.ledger import ICTransaction


def _leg(entity: str, counterparty: str, reference: str, amount: str, txn_date: date = date(2025, 9, 30)) -> ICTransaction:
    return ICTransaction(
        entity_code=entity,
        counterparty_code=counterparty,
        reference=reference,
        amount=Decimal(amount),
        transaction_date=txn_date,
    )


def test_clean_pair_produces_no_exception():
    legs = [
        _leg("US01", "DE01", "MGMT-FEE-2025-1000", "1000.00"),
        _leg("DE01", "US01", "MGMT-FEE-2025-1000", "-1000.00"),
    ]
    result = match_transactions(legs)
    assert len(result.clean_pairs) == 1
    assert result.exceptions == []


def test_missing_counterparty():
    legs = [_leg("US01", "DE01", "REF-2", "5000.00")]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.exception_type == ExceptionType.MISSING_COUNTERPARTY
    assert exc.net_amount == Decimal("5000.00")
