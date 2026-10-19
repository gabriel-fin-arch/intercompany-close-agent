"""Tests for the journal import files a finalized close writes."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_dataset
from intercompany_close_agent.journal import (
    D365_COLUMNS,
    D365_JOURNAL_NAME,
    D365_TEXT_LENGTH,
    GENERIC_COLUMNS,
    d365_csv,
    generic_csv,
    journal_rows,
    period_end,
)
from intercompany_close_agent.models.elimination import JournalLineType

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PREPARER = "Ana Ruiz"
REVIEWER = "Ben Okafor"
APPROVED = "RECHARGE-2025-1000"
BY_THE_PREPARER = "MGMT-FEE-2025-1007"
UNDECIDED = "LOAN-INT-2025-1022"
REJECTED = "ROYALTY-2025-1003"


@pytest.fixture(scope="module")
def final() -> dict:
    """The sample close, finalized with one approval by the reviewer, one by
    the preparer (refused), one item left without a decision, and the rest
    rejected."""
    entities, trial_balance, transactions = load_dataset(DATA_DIR)
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-journal", prepared_by=PREPARER
    )
    decisions = []
    for item in result["__interrupt__"][0].value["pending_review"]:
        reference = item["reference"]
        if reference == UNDECIDED:
            continue
        if reference == APPROVED:
            decisions.append({"reference": reference, "action": "approve", "reviewer": REVIEWER})
        elif reference == BY_THE_PREPARER:
            decisions.append({"reference": reference, "action": "approve", "reviewer": PREPARER})
        else:
            decisions.append({"reference": reference, "action": "reject", "reviewer": REVIEWER})
    return resume_close(graph, config, decisions)


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_every_voucher_balances_and_the_journal_is_the_entries_booked(final: dict):
    rows = journal_rows(final["eliminations"])

    by_voucher: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        assert (row.debit > 0) != (row.credit > 0), row
        by_voucher[row.voucher] += row.debit - row.credit
    assert set(by_voucher.values()) == {Decimal("0")}
    assert len(by_voucher) == len(final["eliminations"])
    assert [row.line for row in rows] == list(range(1, len(rows) + 1))


def test_the_generic_file_reads_back_to_the_runs_totals(final: dict):
    rows = _rows(generic_csv(final))
    booked_debits = sum(
        line.amount for e in final["eliminations"] for line in e.lines if line.line_type is JournalLineType.DEBIT
    )

    assert tuple(rows[0]) == GENERIC_COLUMNS
    assert sum(Decimal(r["debit"]) for r in rows) == sum(Decimal(r["credit"]) for r in rows) == booked_debits
    assert {r["reference"] for r in rows} == {e.reference for e in final["eliminations"]}
    assert {r["posting_date"] for r in rows} == {"2025-09-30"}
    assert {r["journal"] for r in rows} == {"IC-ELIM-2025-09"}
    assert {r["currency"] for r in rows} == {"USD"}


def test_what_the_close_did_not_book_is_not_in_the_journal(final: dict):
    references = {row["reference"] for row in _rows(generic_csv(final))}

    assert APPROVED in references
    assert BY_THE_PREPARER not in references, "approved by the preparer, so refused"
    assert UNDECIDED not in references, "no decision, so still pending"
    assert REJECTED not in references


def test_the_dynamics_file_follows_the_general_journal_entity(final: dict):
    rows = _rows(d365_csv(final))

    assert tuple(rows[0]) == D365_COLUMNS
    for header in ("JOURNALBATCHNUMBER", "JOURNALNAME", "DESCRIPTION", "TRANSDATE", "CURRENCYCODE"):
        assert len({row[header] for row in rows}) == 1, header
    assert rows[0]["JOURNALNAME"] == D365_JOURNAL_NAME
    assert [int(row["LINENUMBER"]) for row in rows] == list(range(1, len(rows) + 1))
    assert {row["ACCOUNTTYPE"] for row in rows} == {"Ledger"}
    assert all(len(row["TEXT"]) <= D365_TEXT_LENGTH for row in rows)

    vouchers: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        vouchers[row["VOUCHER"]].append(row)
    for lines in vouchers.values():
        assert len(lines) <= 10, "Microsoft recommends small physical vouchers"
        assert sum(Decimal(r["DEBITAMOUNT"]) - Decimal(r["CREDITAMOUNT"]) for r in lines) == 0
    assert all(row["DEBITAMOUNT"].count(".") == 1 and len(row["DEBITAMOUNT"].split(".")[1]) == 2 for row in rows)


def test_the_account_carries_the_entity_as_a_dimension_and_maps_the_main_account(final: dict):
    unmapped = _rows(d365_csv(final))
    mapped = _rows(d365_csv(final, main_accounts={"IC_RECEIVABLE": "130500", "IC_PAYABLE": "230500"}))
    generic = _rows(generic_csv(final))

    for plain, d365 in zip(generic, unmapped, strict=True):
        assert d365["ACCOUNTDISPLAYVALUE"] == f"{plain['account']}-{plain['entity']}"
    assert {row["ACCOUNTDISPLAYVALUE"].split("-")[0] for row in mapped} <= {"130500", "230500"}


def test_the_posting_date_is_the_end_of_the_month_the_close_is_for():
    """Not the month of the latest leg: the sample's timing gap is booked in
    October, after a September cutoff."""
    assert period_end([date(2025, 9, 3), date(2025, 9, 22), date(2025, 10, 4)]) == date(2025, 9, 30)
    assert period_end([date(2024, 2, 1)]) == date(2024, 2, 29)
    assert period_end([date(2025, 9, 30), date(2025, 10, 1)]) == date(2025, 10, 31), "a tie takes the later month"
    with pytest.raises(ValueError, match="no transactions"):
        period_end([])


def test_a_group_with_two_reporting_currencies_gets_no_journal(final: dict):
    state = dict(final)
    euro = final["entities"][-1].model_copy(update={"reporting_currency": "EUR"})
    state["entities"] = [*final["entities"][:-1], euro]

    with pytest.raises(ValueError, match="one reporting currency"):
        generic_csv(state)


def test_a_posting_date_can_be_given(final: dict):
    rows = _rows(d365_csv(final, posting_date=date(2025, 9, 29)))

    assert {row["TRANSDATE"] for row in rows} == {"2025-09-29"}
