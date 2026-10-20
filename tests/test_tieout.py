"""Tests for the trial balance control-account tie-out."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from intercompany_close_agent.ingest.loaders import load_ic_transactions, load_trial_balance
from intercompany_close_agent.models.ledger import ICTransaction, TrialBalanceLine
from intercompany_close_agent.policy import DEFAULT_POLICY
from intercompany_close_agent.reconciliation.tieout import out_of_tolerance, reconcile_to_trial_balance

TIEOUT_TOLERANCE = DEFAULT_POLICY.tieout_tolerance


def _leg(entity: str, amount: str) -> ICTransaction:
    return ICTransaction(
        entity_code=entity,
        counterparty_code="ZZ99",
        reference="REF",
        amount=Decimal(amount),
        transaction_date=date(2025, 9, 30),
    )


def _tb(entity: str, account: str, balance: str) -> TrialBalanceLine:
    return TrialBalanceLine(
        entity_code=entity,
        account_code=account,
        account_name=account,
        balance=Decimal(balance),
    )


def test_entity_that_ties_is_within_tolerance():
    transactions = [_leg("US01", "1000.00"), _leg("US01", "-400.00")]
    trial_balance = [
        _tb("US01", "IC_RECEIVABLE", "1000.00"),
        _tb("US01", "IC_PAYABLE", "-400.00"),
    ]

    variances = reconcile_to_trial_balance(transactions, trial_balance)

    assert len(variances) == 1
    assert variances[0].variance == Decimal("0.00")
    assert variances[0].within_tolerance
    assert out_of_tolerance(variances) == []


def test_variance_is_flagged_when_the_gl_has_a_posting_the_subledger_lacks():
    transactions = [_leg("US01", "1000.00")]
    trial_balance = [_tb("US01", "IC_RECEIVABLE", "1250.00")]

    variances = reconcile_to_trial_balance(transactions, trial_balance)

    assert variances[0].variance == Decimal("-250.00")
    assert not variances[0].within_tolerance
    assert len(out_of_tolerance(variances)) == 1


def test_rounding_noise_stays_within_tolerance():
    transactions = [_leg("US01", "1000.00")]
    trial_balance = [_tb("US01", "IC_RECEIVABLE", str(Decimal("1000.00") + TIEOUT_TOLERANCE))]

    variances = reconcile_to_trial_balance(transactions, trial_balance)

    assert variances[0].within_tolerance


def test_non_ic_accounts_are_ignored():
    """Only the IC control accounts count -- the rest of the TB is irrelevant here."""
    transactions = [_leg("US01", "1000.00")]
    trial_balance = [
        _tb("US01", "IC_RECEIVABLE", "1000.00"),
        _tb("US01", "CASH", "999999.00"),
        _tb("US01", "REVENUE", "-500000.00"),
    ]

    variances = reconcile_to_trial_balance(transactions, trial_balance)

    assert variances[0].within_tolerance


def test_entity_present_on_only_one_side_still_reported():
    """An entity in the subledger but absent from the TB is itself a variance."""
    transactions = [_leg("BR01", "750.00")]
    trial_balance: list[TrialBalanceLine] = []

    variances = reconcile_to_trial_balance(transactions, trial_balance)

    assert variances[0].entity_code == "BR01"
    assert variances[0].trial_balance_total == Decimal("0")
    assert not variances[0].within_tolerance


def test_against_the_real_synthetic_dataset():
    """The shipped dataset ties for every entity except the one deliberately broken."""
    data_dir = Path(__file__).resolve().parent.parent / "data" / "synthetic"
    transactions = load_ic_transactions(data_dir / "ic_ledger.csv")
    trial_balance = load_trial_balance(data_dir / "trial_balance.csv")

    variances = reconcile_to_trial_balance(transactions, trial_balance)
    breaks = out_of_tolerance(variances)

    assert len(variances) == 7
    assert len(breaks) == 1, "the generator injects exactly one control account break"
