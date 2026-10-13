"""Tests for the trial balance and IC ledger loaders."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from intercompany_close_agent.ingest.loaders import (
    DataLoadError,
    load_dataset,
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


def test_a_bad_amount_names_the_file_and_the_line(tmp_csv_dir):
    csv_path = tmp_csv_dir / "ic_ledger.csv"
    csv_path.write_text(
        "entity_code,counterparty_code,reference,amount,currency,transaction_date,description\n"
        "US01,DE01,MGMT-FEE-2025-1000,1000.00,USD,2025-09-15,Mgmt fee\n"
        "DE01,US01,MGMT-FEE-2025-1000,abc,USD,2025-09-15,Mgmt fee\n",
        encoding="utf-8",
    )

    with pytest.raises(DataLoadError, match=r"ic_ledger\.csv line 3: could not parse amount: 'abc'"):
        load_ic_transactions(csv_path)


def test_a_missing_column_is_named_rather_than_a_key_error(tmp_csv_dir):
    csv_path = tmp_csv_dir / "ic_ledger.csv"
    csv_path.write_text(
        "entity_code,counterparty_code,reference,amt,currency,transaction_date\n"
        "US01,DE01,MGMT-FEE-2025-1000,1000.00,USD,2025-09-15\n",
        encoding="utf-8",
    )

    with pytest.raises(DataLoadError, match="missing column"):
        load_ic_transactions(csv_path)


def test_a_zero_byte_file_is_refused(tmp_csv_dir):
    csv_path = tmp_csv_dir / "trial_balance.csv"
    csv_path.write_text("", encoding="utf-8")

    with pytest.raises(DataLoadError, match="empty"):
        load_trial_balance(csv_path)


def _write_dataset(directory: Path, ledger_rows: str, entities: str = "US01,DE01") -> None:
    rows = "".join(f"{code},{code} Ltd,EMEA,USD,USD,True\n" for code in entities.split(","))
    (directory / "entities.csv").write_text(
        "code,name,region,local_currency,reporting_currency,interfaced\n" + rows, encoding="utf-8"
    )
    (directory / "trial_balance.csv").write_text(
        "entity_code,account_code,account_name,balance\nUS01,1000-IC-REC,Intercompany Receivable,1000.00\n",
        encoding="utf-8",
    )
    (directory / "ic_ledger.csv").write_text(
        "entity_code,counterparty_code,reference,amount,currency,transaction_date,description\n" + ledger_rows,
        encoding="utf-8",
    )


def test_a_ledger_with_no_rows_is_not_a_clean_close(tmp_csv_dir):
    """Every step downstream accepts an empty list, so this used to come out as
    'no items needed human review' -- a clean month, from a feed that never came."""
    _write_dataset(tmp_csv_dir, ledger_rows="")

    with pytest.raises(DataLoadError, match="nothing to close"):
        load_dataset(tmp_csv_dir)


def test_an_entity_missing_from_the_master_data_is_refused(tmp_csv_dir):
    """Triage reads `interfaced` off the master data. An entity it has never heard
    of would otherwise be treated as one that loads through a system interface."""
    _write_dataset(
        tmp_csv_dir,
        ledger_rows=(
            "US01,ZZ99,MGMT-FEE-2025-1000,1000.00,USD,2025-09-15,Mgmt fee\n"
            "ZZ99,US01,MGMT-FEE-2025-1000,-1000.00,USD,2025-09-15,Mgmt fee\n"
        ),
    )

    with pytest.raises(DataLoadError, match="ZZ99"):
        load_dataset(tmp_csv_dir)


def test_the_committed_sample_passes_the_cross_file_checks():
    data_dir = Path(__file__).resolve().parent.parent / "data" / "synthetic"

    entities, trial_balance, transactions = load_dataset(data_dir)

    assert entities and trial_balance and transactions
