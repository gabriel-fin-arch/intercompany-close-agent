"""Tests for close.xlsx, the evidence pack as one workbook."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from intercompany_close_agent.evidence import pack_files, write_pack, zip_pack
from intercompany_close_agent.evidence_workbook import SHEETS, close_xlsx
from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_dataset

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PREPARER = "Ana Ruiz"
REVIEWER = "Ben Okafor"


@pytest.fixture
def workbook(final_state: dict):
    files = pack_files(final_state, DATA_DIR)
    return files, load_workbook(io.BytesIO(close_xlsx(files)))


@pytest.fixture
def final_state(monkeypatch) -> dict:
    """The sample close, finalized: one approval by the reviewer, one by the
    preparer (which finalize refuses), everything else rejected."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    entities, trial_balance, transactions = load_dataset(DATA_DIR)
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-evidence-workbook", prepared_by=PREPARER
    )
    decisions = []
    for item in result["__interrupt__"][0].value["pending_review"]:
        reference = item["reference"]
        action = "approve" if reference == "RECHARGE-2025-1000" else "reject"
        decisions.append({"reference": reference, "action": action, "reviewer": REVIEWER})
    return resume_close(graph, config, decisions)


def _sheet_rows(sheet) -> list[list[str]]:
    """A sheet's data rows as display text, None for blanks, for comparing
    against the CSV the sheet came from."""
    rows = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        rows.append(["" if value is None else str(value) for value in row])
    return rows


def test_one_sheet_per_csv_plus_the_run_sheet(workbook):
    _, wb = workbook
    assert wb.sheetnames == ["run", *SHEETS]


def test_every_sheet_matches_its_csv(workbook):
    files, wb = workbook
    for name in SHEETS:
        csv_rows = list(csv.reader(io.StringIO(files[f"{name}.csv"])))
        sheet = wb[name]
        assert [cell.value for cell in sheet[1]] == csv_rows[0], name
        sheet_rows = _sheet_rows(sheet)
        assert len(sheet_rows) == len(csv_rows) - 1, name
        for sheet_row, csv_row in zip(sheet_rows, csv_rows[1:], strict=True):
            for sheet_value, csv_value in zip(sheet_row, csv_row, strict=True):
                if csv_value == "":
                    assert sheet_value == "", (name, csv_row)
                elif sheet_value != csv_value:
                    # typed cells: a date's text starts with the ISO date, a
                    # number formats back to the same value
                    if sheet_value.startswith(csv_value[:10]):
                        continue
                    assert float(sheet_value) == float(csv_value), (name, sheet_value, csv_value)


def test_amounts_are_numbers_and_dates_are_dates(workbook):
    _, wb = workbook
    eliminations = wb["eliminations"]
    amount_column = [cell.value for cell in eliminations[1]].index("amount") + 1
    cell = eliminations.cell(row=2, column=amount_column)
    assert isinstance(cell.value, float)
    assert cell.number_format == "#,##0.00"

    decisions = wb["decisions"]
    decided_column = [cell.value for cell in decisions[1]].index("decided_at") + 1
    assert isinstance(decisions.cell(row=2, column=decided_column).value, datetime)

    journal = wb["journal"]
    date_column = [cell.value for cell in journal[1]].index("posting_date") + 1
    assert isinstance(journal.cell(row=2, column=date_column).value, date)


def test_headers_are_frozen_and_filtered(workbook):
    _, wb = workbook
    for name in wb.sheetnames:
        assert wb[name].freeze_panes == "A2", name
        assert wb[name].auto_filter.ref is not None, name


def test_the_run_sheet_says_who_when_and_under_what_policy(workbook):
    files, wb = workbook
    run = json.loads(files["run.json"])
    rows = {cell[0].value: cell[1].value for cell in wb["run"].iter_rows(min_row=2)}
    assert rows["prepared_by"] == PREPARER
    assert rows["reviewers"] == ", ".join(run["reviewers"])
    assert rows["policy.materiality_threshold"] == float(run["policy"]["materiality_threshold"])
    assert rows["counts.eliminations"] == run["counts"]["eliminations"]
    assert isinstance(rows["generated_at"], datetime)


def test_the_same_pack_gives_the_same_workbook_byte_for_byte(final_state: dict):
    files = pack_files(final_state, DATA_DIR)
    assert close_xlsx(files) == close_xlsx(files)


def test_a_written_pack_contains_the_workbook_and_zips_it(final_state: dict, tmp_path: Path):
    folder = write_pack(final_state, tmp_path, DATA_DIR)
    workbook_bytes = (folder / "close.xlsx").read_bytes()
    assert load_workbook(io.BytesIO(workbook_bytes)).sheetnames == ["run", *SHEETS]
    with zipfile.ZipFile(io.BytesIO(zip_pack(folder))) as archive:
        assert archive.read(f"{folder.name}/close.xlsx") == workbook_bytes
