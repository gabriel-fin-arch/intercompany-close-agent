"""Tests for elimination JE generation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from intercompany_close_agent.eliminations.engine import (
    build_elimination,
    build_elimination_from_exception,
    build_elimination_from_known_leg,
    build_eliminations,
)
from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
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


def test_elimination_clears_the_control_accounts_the_tieout_reads():
    """The entry has to hit IC_PAYABLE / IC_RECEIVABLE, not a generic bucket --
    otherwise the control accounts survive the elimination at group level."""
    from intercompany_close_agent.reconciliation.tieout import (
        IC_PAYABLE_ACCOUNT,
        IC_RECEIVABLE_ACCOUNT,
    )

    pair = (
        _leg("US01", "DE01", "REF-CTRL", "1000.00"),
        _leg("DE01", "US01", "REF-CTRL", "-1000.00"),
    )
    elim = build_elimination(pair)

    debit = next(line for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    credit = next(line for line in elim.lines if line.line_type == JournalLineType.CREDIT)
    assert debit.account_code == IC_PAYABLE_ACCOUNT
    assert credit.account_code == IC_RECEIVABLE_ACCOUNT


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


def test_zero_value_pairs_produce_no_entry():
    """There's nothing to eliminate, so posting a zero entry would be noise."""
    pairs = [(_leg("US01", "DE01", "REF-Z", "0.00"), _leg("DE01", "US01", "REF-Z", "0.00"))]
    assert build_eliminations(pairs) == []


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


def test_journal_line_rejects_a_non_positive_amount():
    """The debit/credit side is carried by line_type, so the amount is always
    positive -- a negative or zero would either invert the direction or book
    nothing. The Field documents this; enforce it so it can't be violated."""
    for bad in (Decimal("-100.00"), Decimal("0")):
        with pytest.raises(ValueError, match="greater than 0"):
            JournalLine(
                entity_code="US01",
                account_code="9999-IC-ELIM",
                line_type=JournalLineType.DEBIT,
                amount=bad,
            )


def test_build_elimination_from_exception_refuses_a_non_positive_override():
    """A reviewer's override is the one human-supplied number that reaches a
    JE. A negative one would post a direction-inverted 'balanced' entry; a
    zero would clear nothing. The model backstop must refuse both."""
    exc = ICException(
        reference="REF-NEG",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        legs=[_leg("US01", "DE01", "REF-NEG", "1000.00"), _leg("DE01", "US01", "REF-NEG", "-950.00")],
        net_amount=Decimal("50.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )
    for bad in (Decimal("-500.00"), Decimal("0")):
        with pytest.raises(ValueError, match="greater than 0"):
            build_elimination_from_exception(exc, override_amount=bad)


def test_build_elimination_from_known_leg_refuses_a_non_positive_amount():
    known = _leg("US01", "DE01", "REF-MC", "5000.00")
    for bad in (Decimal("-5000.00"), Decimal("0")):
        with pytest.raises(ValueError, match="greater than 0"):
            build_elimination_from_known_leg(known, bad)


def test_build_elimination_from_exception_uses_the_raw_amount_by_default():
    exc = ICException(
        reference="REF-5",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        legs=[_leg("US01", "DE01", "REF-5", "1000.00"), _leg("DE01", "US01", "REF-5", "-950.00")],
        net_amount=Decimal("50.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )
    elim = build_elimination_from_exception(exc)
    debits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    credits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.CREDIT)
    assert debits == credits == Decimal("1000.00")  # the receivable leg's amount, not the residual

    # DE01 only ever booked -950.00, so this entry debits its IC_PAYABLE for
    # 1000.00 -- 50.00 more than DE01 actually owed. That's not free: DE01's
    # control account flips to a 50.00 receivable instead of landing at
    # zero, and the narrative has to say so rather than letting the gap
    # disappear. Negative means over-cleared; see elimination_residuals.
    assert "DE01 carries an unexplained residual of -50.00 after posting" in elim.narrative


def test_build_elimination_from_exception_honors_override_amount():
    exc = ICException(
        reference="REF-6",
        exception_type=ExceptionType.TIMING_GAP,
        legs=[_leg("US01", "DE01", "REF-6", "1000.00"), _leg("DE01", "US01", "REF-6", "-1000.00")],
        net_amount=Decimal("0.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )
    elim = build_elimination_from_exception(exc, override_amount=Decimal("800.00"))
    debits = sum(line.amount for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    assert debits == Decimal("800.00")


def test_elimination_from_exception_leaves_no_residual_note_when_it_fully_clears():
    """The common case -- both legs booked the same amount -- shouldn't get
    a residual note just because one exists to check for."""
    exc = ICException(
        reference="REF-CLEAN",
        exception_type=ExceptionType.TIMING_GAP,
        legs=[_leg("US01", "DE01", "REF-CLEAN", "1000.00"), _leg("DE01", "US01", "REF-CLEAN", "-1000.00")],
        net_amount=Decimal("0.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )
    elim = build_elimination_from_exception(exc)
    assert "residual" not in elim.narrative


def test_elimination_residuals_reports_per_entity_gap():
    from intercompany_close_agent.eliminations.engine import elimination_residuals

    exc = ICException(
        reference="REF-RES",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        legs=[_leg("DE01", "ZA01", "REF-RES", "181350.76"), _leg("ZA01", "DE01", "REF-RES", "-182493.27")],
        net_amount=Decimal("-1142.51"),
        materiality=Materiality.HIGH,
        detected_reason="test fixture",
    )
    elim = build_elimination_from_exception(exc)

    residuals = dict(elimination_residuals(exc.legs, elim))
    assert residuals == {"ZA01": Decimal("1142.51")}
    # DE01 (the receivable leg) is always cleared exactly when there's no override
    assert "DE01" not in residuals


def test_build_elimination_from_exception_rejects_wrong_leg_count():
    exc = ICException(
        reference="REF-7",
        exception_type=ExceptionType.MISSING_COUNTERPARTY,
        legs=[_leg("US01", "DE01", "REF-7", "1000.00")],
        net_amount=Decimal("1000.00"),
        materiality=Materiality.HIGH,
        detected_reason="test fixture",
    )
    with pytest.raises(ValueError, match="cannot build an elimination"):
        build_elimination_from_exception(exc)


def test_build_elimination_refuses_to_guess_direction_for_same_signed_legs():
    """A sign-flip pair (both receivable, or both payable) has no honest
    receivable/payable split -- this must raise, not silently invert one
    side of the entry."""
    exc = ICException(
        reference="REF-SIGN",
        exception_type=ExceptionType.SIGN_MISMATCH,
        legs=[_leg("US01", "DE01", "REF-SIGN", "1000.00"), _leg("DE01", "US01", "REF-SIGN", "1000.00")],
        net_amount=Decimal("2000.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )
    with pytest.raises(ValueError, match="cannot tell receivable from payable"):
        build_elimination_from_exception(exc)


def test_known_leg_receivable_credits_the_booking_entity():
    # US01 booked a receivable from DE01; DE01 never booked its side.
    leg = _leg("US01", "DE01", "REF-8", "1000.00")
    elim = build_elimination_from_known_leg(leg, Decimal("1000.00"))

    debit = next(line for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    credit = next(line for line in elim.lines if line.line_type == JournalLineType.CREDIT)
    assert debit.entity_code == "DE01"  # the one that owes
    assert credit.entity_code == "US01"  # the one that's owed
    assert debit.amount == credit.amount == Decimal("1000.00")


def test_known_leg_payable_swaps_the_sides():
    # Same pair, but the surviving leg is the payable side.
    leg = _leg("US01", "DE01", "REF-9", "-1000.00")
    elim = build_elimination_from_known_leg(leg, Decimal("1000.00"))

    debit = next(line for line in elim.lines if line.line_type == JournalLineType.DEBIT)
    credit = next(line for line in elim.lines if line.line_type == JournalLineType.CREDIT)
    assert debit.entity_code == "US01"
    assert credit.entity_code == "DE01"


def test_known_leg_uses_the_reviewer_supplied_amount_not_the_booked_one():
    leg = _leg("US01", "DE01", "REF-10", "1000.00")
    elim = build_elimination_from_known_leg(leg, Decimal("750.00"), note="agreed with DE01 controller")

    assert all(line.amount == Decimal("750.00") for line in elim.lines)
    assert "agreed with DE01 controller" in elim.narrative


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
