"""Tests for the deterministic IC matching engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from intercompany_close_agent.matching.engine import (
    AMOUNT_TOLERANCE,
    MATERIALITY_THRESHOLD,
    TIMING_TOLERANCE_DAYS,
    match_transactions,
)
from intercompany_close_agent.models.exception import ExceptionType, Materiality
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


def test_rounding_within_tolerance_is_a_clean_match():
    legs = [
        _leg("US01", "DE01", "REF-3", "1000.00"),
        _leg("DE01", "US01", "REF-3", str(-Decimal("1000.00") + AMOUNT_TOLERANCE)),  # right at the edge
    ]
    result = match_transactions(legs)
    assert len(result.clean_pairs) == 1
    assert result.exceptions == []


def test_counterparty_mismatch():
    legs = [
        _leg("US01", "DE01", "REF-4", "2000.00"),
        _leg("GB01", "MX01", "REF-4", "-2000.00"),  # booked against the wrong entity entirely
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.COUNTERPARTY_MISMATCH


def test_amount_mismatch_from_sign_flip():
    legs = [
        _leg("US01", "DE01", "REF-5", "3000.00"),
        _leg("DE01", "US01", "REF-5", "3000.00"),  # should have been -3000.00
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.exception_type == ExceptionType.AMOUNT_MISMATCH
    assert exc.net_amount == Decimal("6000.00")


def test_amount_mismatch_materiality_bands():
    small = [
        _leg("US01", "DE01", "REF-6", "500.00"),
        _leg("DE01", "US01", "REF-6", str(-Decimal("500.00") + Decimal("50.00"))),  # off by 50, below materiality
    ]
    result_small = match_transactions(small)
    assert result_small.exceptions[0].materiality == Materiality.LOW

    large = [
        _leg("US01", "DE01", "REF-7", "500000.00"),
        _leg("DE01", "US01", "REF-7", str(-Decimal("500000.00") + MATERIALITY_THRESHOLD)),
    ]
    result_large = match_transactions(large)
    assert result_large.exceptions[0].materiality == Materiality.HIGH


def test_timing_gap_flagged_even_when_amounts_match():
    legs = [
        _leg("US01", "DE01", "REF-8", "1000.00", txn_date=date(2025, 9, 20)),
        _leg("DE01", "US01", "REF-8", "-1000.00", txn_date=date(2025, 9, 29)),  # 9 days later
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.TIMING_GAP


def test_timing_within_tolerance_is_clean():
    # exactly TIMING_TOLERANCE_DAYS apart -- right at the boundary, still clean
    assert TIMING_TOLERANCE_DAYS == 2
    legs = [
        _leg("US01", "DE01", "REF-9", "1000.00", txn_date=date(2025, 9, 28)),
        _leg("DE01", "US01", "REF-9", "-1000.00", txn_date=date(2025, 9, 30)),
    ]
    result = match_transactions(legs)
    assert result.exceptions == []
    assert len(result.clean_pairs) == 1


def test_duplicate_reference_flagged():
    legs = [
        _leg("US01", "DE01", "REF-10", "1000.00"),
        _leg("DE01", "US01", "REF-10", "-1000.00"),
        _leg("GB01", "US01", "REF-10", "1000.00"),  # a third leg sharing the same reference
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.DUPLICATE_REFERENCE


def test_against_the_real_synthetic_dataset():
    """Sanity check against the generator's actual output, not just hand-built fixtures."""
    from pathlib import Path

    from intercompany_close_agent.ingest.loaders import load_ic_transactions

    csv_path = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "ic_ledger.csv"
    transactions = load_ic_transactions(csv_path)

    result = match_transactions(transactions)

    # every leg is accounted for, either in a clean pair or an exception
    legs_in_pairs = len(result.clean_pairs) * 2
    legs_in_exceptions = sum(len(exc.legs) for exc in result.exceptions)
    assert legs_in_pairs + legs_in_exceptions == len(transactions)

    # the dataset was generated with real anomalies -- there should be some of both
    assert len(result.clean_pairs) > 0
    assert len(result.exceptions) > 0
