"""Tests for elimination JE generation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from intercompany_close_agent.eliminations.engine import build_elimination, build_eliminations
from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.ledger import ICTransaction


def _leg(entity: str, counterparty: str, reference: str, amount: str) -> ICTransaction:
    return ICTransaction(
        entity_code=entity,
        counterparty_code=counterparty,
        reference=reference,
        amount=Decimal(amount),
        transaction_date=date(2025, 9, 30),
    )


def test_build_elimination_balances():
    pair = (
        _leg("US01", "DE01", "MGMT-FEE-2025-1000", "1000.00"),
        _leg("DE01", "US01", "MGMT-FEE-2025-1000", "-1000.00"),
    )
    elim = build_elimination(pair)
    debits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    credits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.CREDIT)
    assert debits == credits == Decimal("1000.00")


def test_build_elimination_debits_the_payable_credits_the_receivable():
    pair = (
        _leg("US01", "DE01", "REF-1", "1000.00"),  # US01 is owed -> receivable
        _leg("DE01", "US01", "REF-1", "-1000.00"),  # DE01 owes -> payable
    )
    elim = build_elimination(pair)
    debit_line = next(line for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    credit_line = next(line for line in elim.lines if line.line_type == JournalLineType.CREDIT)
    assert debit_line.entity_code == "DE01"
    assert credit_line.entity_code == "US01"


def test_build_elimination_order_independent():
    """The pair can arrive in either order -- same elimination either way."""
    pair_forward = (
        _leg("US01", "DE01", "REF-2", "500.00"),
        _leg("DE01", "US01", "REF-2", "-500.00"),
    )
    pair_reversed = (pair_forward[1], pair_forward[0])

    elim_forward = build_elimination(pair_forward)
    elim_reversed = build_elimination(pair_reversed)

    assert {(line.entity_code, line.line_type) for line in elim_forward.lines} == {
        (line.entity_code, line.line_type) for line in elim_reversed.lines
    }


def test_build_eliminations_batch():
    pairs = [
        (_leg("US01", "DE01", "REF-3", "100.00"), _leg("DE01", "US01", "REF-3", "-100.00")),
        (_leg("GB01", "MX01", "REF-4", "200.00"), _leg("MX01", "GB01", "REF-4", "-200.00")),
    ]
    eliminations = build_eliminations(pairs)
    assert len(eliminations) == 2
    assert {e.reference for e in eliminations} == {"REF-3", "REF-4"}


def test_elimination_model_rejects_unbalanced_lines():
    with pytest.raises(ValueError, match="does not balance"):
        Elimination(
            reference="BAD-REF",
            lines=[
                JournalLine(
                    entity_code="US01",
                    account_code="9999-IC-ELIM",
                    line_type=JournalLineType.DEBIT,
                    amount=Decimal("100.00"),
                ),
                JournalLine(
                    entity_code="DE01",
                    account_code="9999-IC-ELIM",
                    line_type=JournalLineType.CREDIT,
                    amount=Decimal("99.00"),
                ),
            ],
        )


def test_against_the_real_synthetic_dataset():
    """Run eliminations end to end against the matcher's output on real data."""
    from pathlib import Path

    from intercompany_close_agent.ingest.loaders import load_ic_transactions
    from intercompany_close_agent.matching.engine import match_transactions

    csv_path = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "ic_ledger.csv"
    transactions = load_ic_transactions(csv_path)
    result = match_transactions(transactions)

    eliminations = build_eliminations(result.clean_pairs)

    assert len(eliminations) == len(result.clean_pairs)
    for elim in eliminations:
        debits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.DEBIT)
        credits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.CREDIT)
        assert debits == credits
