"""Tests for the deterministic IC matching engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from intercompany_close_agent.matching.engine import (
    AMOUNT_TOLERANCE_FLOOR,
    AMOUNT_TOLERANCE_RATE,
    MATERIALITY_THRESHOLD,
    amount_tolerance_for,
    match_transactions,
)
from intercompany_close_agent.models.exception import ExceptionType, Materiality
from intercompany_close_agent.models.ledger import ICTransaction


def _leg(
    entity: str,
    counterparty: str,
    reference: str,
    amount: str,
    txn_date: date = date(2025, 9, 30),
) -> ICTransaction:
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
        _leg("DE01", "US01", "REF-3", str(-Decimal("1000.00") + AMOUNT_TOLERANCE_FLOOR)),  # at the edge
    ]
    result = match_transactions(legs)
    assert len(result.clean_pairs) == 1
    assert result.exceptions == []


def test_tolerance_scales_with_the_size_of_the_balance():
    """A flat tolerance would treat a small balance and a large one alike."""
    assert amount_tolerance_for(Decimal("500.00")) == AMOUNT_TOLERANCE_FLOOR  # floor applies
    assert amount_tolerance_for(Decimal("1000000.00")) == Decimal("1000000.00") * AMOUNT_TOLERANCE_RATE

    # a 50-dollar break on a 500-dollar balance is a real difference
    small = [
        _leg("US01", "DE01", "REF-S", "500.00"),
        _leg("DE01", "US01", "REF-S", "-450.00"),
    ]
    assert len(match_transactions(small).exceptions) == 1

    # the same 50 dollars on a 5,000,000 balance is noise
    large = [
        _leg("US01", "DE01", "REF-L", "5000000.00"),
        _leg("DE01", "US01", "REF-L", "-4999950.00"),
    ]
    assert len(match_transactions(large).clean_pairs) == 1


def test_fx_drift_still_fails_despite_the_relative_tolerance():
    """The relative rate is sized well below real FX drift, so it can't hide it."""
    legs = [
        _leg("US01", "DE01", "REF-FXD", "100000.00"),
        _leg("DE01", "US01", "REF-FXD", "-100200.00"),  # 0.2% apart, typical rate drift
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.AMOUNT_MISMATCH


def test_counterparty_mismatch():
    legs = [
        _leg("US01", "DE01", "REF-4", "2000.00"),
        _leg("GB01", "MX01", "REF-4", "-2000.00"),  # booked against the wrong entity entirely
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.COUNTERPARTY_MISMATCH


def test_sign_flip_is_a_sign_mismatch_not_an_amount_mismatch():
    """Both legs booked on the same side is a different failure mode from an
    amount that's merely off: there's no residual to band, and no way to
    tell which entity has the sign backwards. It must never be lumped in
    with AMOUNT_MISMATCH, which eliminations/engine.py trusts to always have
    one receivable leg and one payable leg."""
    legs = [
        _leg("US01", "DE01", "REF-5", "3000.00"),
        _leg("DE01", "US01", "REF-5", "3000.00"),  # should have been -3000.00
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.exception_type == ExceptionType.SIGN_MISMATCH
    assert exc.net_amount == Decimal("6000.00")


def test_sign_mismatch_materiality_is_the_balance_at_risk():
    legs = [
        _leg("US01", "DE01", "REF-SIGN-BIG", "500000.00"),
        _leg("DE01", "US01", "REF-SIGN-BIG", "500000.00"),  # both receivable
    ]
    result = match_transactions(legs)
    assert result.exceptions[0].materiality == Materiality.HIGH


def test_a_leg_with_zero_amount_is_not_a_sign_mismatch():
    """Zero has no sign, so it shouldn't trip the same-direction check --
    whatever's wrong with a zero-amount leg, it isn't this."""
    legs = [
        _leg("US01", "DE01", "REF-ZERO", "0.00"),
        _leg("DE01", "US01", "REF-ZERO", "0.00"),
    ]
    result = match_transactions(legs)
    assert result.clean_pairs and not result.exceptions


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


def test_legs_straddling_a_period_end_are_a_timing_gap():
    """One day apart, but on opposite sides of the close -- a real cutoff break."""
    legs = [
        _leg("US01", "DE01", "REF-8", "1000.00", txn_date=date(2025, 9, 30)),
        _leg("DE01", "US01", "REF-8", "-1000.00", txn_date=date(2025, 10, 1)),
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.TIMING_GAP


def test_a_wide_gap_inside_one_period_is_clean():
    """Twenty days apart, but both land in the same close -- nothing to chase."""
    legs = [
        _leg("US01", "DE01", "REF-9", "1000.00", txn_date=date(2025, 9, 8)),
        _leg("DE01", "US01", "REF-9", "-1000.00", txn_date=date(2025, 9, 28)),
    ]
    result = match_transactions(legs)
    assert result.exceptions == []
    assert len(result.clean_pairs) == 1


def test_an_entity_cannot_be_its_own_counterparty():
    """Self-dealing balances net to zero and would silently pass as clean."""
    legs = [
        _leg("US01", "US01", "REF-SELF", "1000.00"),
        _leg("US01", "US01", "REF-SELF", "-1000.00"),
    ]
    result = match_transactions(legs)

    assert result.clean_pairs == []
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.SELF_DEALING


def test_self_dealing_caught_even_on_a_single_leg():
    legs = [_leg("DE01", "DE01", "REF-SELF-1", "500.00")]
    result = match_transactions(legs)

    assert result.exceptions[0].exception_type == ExceptionType.SELF_DEALING


def test_currency_mismatch_is_never_netted():
    """Two legs in different currencies must not be netted at an implicit 1:1."""
    legs = [
        ICTransaction(
            entity_code="US01",
            counterparty_code="DE01",
            reference="REF-FX",
            amount=Decimal("1000.00"),
            currency="USD",
            transaction_date=date(2025, 9, 30),
        ),
        ICTransaction(
            entity_code="DE01",
            counterparty_code="US01",
            reference="REF-FX",
            amount=Decimal("-1000.00"),
            currency="EUR",
            transaction_date=date(2025, 9, 30),
        ),
    ]
    result = match_transactions(legs)

    # amounts net to zero, so without the currency check this would look clean
    assert result.clean_pairs == []
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.CURRENCY_MISMATCH
    # None, not zero -- there's nothing to sum across two different
    # currencies, and a literal 0 would misleadingly read as "these net fine"
    assert result.exceptions[0].net_amount is None


def test_duplicate_reference_flagged():
    legs = [
        _leg("US01", "DE01", "REF-10", "1000.00"),
        _leg("DE01", "US01", "REF-10", "-1000.00"),
        _leg("GB01", "US01", "REF-10", "1000.00"),  # a third leg sharing the same reference
    ]
    result = match_transactions(legs)
    assert len(result.exceptions) == 1
    assert result.exceptions[0].exception_type == ExceptionType.DUPLICATE_REFERENCE


def test_summary_counts_by_type():
    legs = [
        _leg("US01", "DE01", "REF-11", "1000.00"),
        _leg("DE01", "US01", "REF-11", "-1000.00"),
        _leg("US01", "GB01", "REF-12", "500.00"),  # missing counterparty
    ]
    result = match_transactions(legs)
    summary = result.summary()
    assert summary["clean_pairs"] == 1
    assert summary["missing_counterparty"] == 1


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
