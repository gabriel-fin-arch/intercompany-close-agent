"""Tests for the trial balance and IC ledger loaders."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from intercompany_close_agent.ingest.loaders import (
    load_ic_transactions,
    load_trial_balance,
    map_account_code,
)


def test_map_account_code_known_mapping():
    assert map_account_code("1000-IC-REC") == "IC_RECEIVABLE"
    assert map_account_code("2000-IC-PAY") == "IC_PAYABLE"


def test_map_account_code_unknown_falls_back_to_local_code():
    # An unmapped account should surface downstream, not disappear.
    assert map_account_code("9999-UNKNOWN") == "9999-UNKNOWN"


@pytest.fixture
def tmp_csv_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def test_load_trial_balance(tmp_csv_dir):
    csv_path = tmp_csv_dir / "tb.csv"
    csv_path.write_text(
        "entity_code,account_code,account_name,balance\n"
        "US01,1000-IC-REC,Intercompany Receivable,1234.56\n"
        "US01,4000-REV,Revenue,-500000.00\n",
        encoding="utf-8",
    )

    lines = load_trial_balance(csv_path)

    assert len(lines) == 2
    assert lines[0].entity_code == "US01"
    # mapped, not the raw local code
    assert lines[0].account_code == "IC_RECEIVABLE"
    assert lines[0].balance == Decimal("1234.56")
    assert lines[1].account_code == "REVENUE"


def test_load_ic_transactions(tmp_csv_dir):
    csv_path = tmp_csv_dir / "ic.csv"
    csv_path.write_text(
        "entity_code,counterparty_code,reference,amount,currency,transaction_date,description\n"
        "US01,DE01,MGMT-FEE-2025-1000,1000.00,USD,2025-09-15,Mgmt fee\n"
        "DE01,US01,MGMT-FEE-2025-1000,-1000.00,USD,2025-09-15,Mgmt fee\n",
        encoding="utf-8",
    )

    transactions = load_ic_transactions(csv_path)

    assert len(transactions) == 2
    assert transactions[0].amount == Decimal("1000.00")
    assert transactions[1].amount == Decimal("-1000.00")
    assert transactions[0].counterparty_code == "DE01"


def test_load_trial_balance_rejects_unparseable_amount(tmp_csv_dir):
    csv_path = tmp_csv_dir / "bad_tb.csv"
    csv_path.write_text(
        "entity_code,account_code,account_name,balance\nUS01,1000-IC-REC,Intercompany Receivable,not-a-number\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="could not parse amount"):
        load_trial_balance(csv_path)
