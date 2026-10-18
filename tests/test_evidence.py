"""Tests for the evidence pack a finalized close writes."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from intercompany_close_agent import evidence
from intercompany_close_agent.cli import app
from intercompany_close_agent.evidence import PACK_FILES, pack_files, write_pack, zip_pack
from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_dataset

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PREPARER = "Ana Ruiz"
REVIEWER = "Ben Okafor"
APPROVED = "RECHARGE-2025-1000"
BY_THE_PREPARER = "MGMT-FEE-2025-1007"


@pytest.fixture
def final(monkeypatch) -> dict:
    """The sample close, finalized: one approval by the reviewer, one by the
    preparer (which finalize refuses), everything else rejected."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    entities, trial_balance, transactions = load_dataset(DATA_DIR)
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-evidence", prepared_by=PREPARER
    )
    decisions = []
    for item in result["__interrupt__"][0].value["pending_review"]:
        reference = item["reference"]
        if reference == APPROVED:
            decisions.append({"reference": reference, "action": "approve", "reviewer": REVIEWER})
        elif reference == BY_THE_PREPARER:
            decisions.append({"reference": reference, "action": "approve", "reviewer": PREPARER})
        else:
            decisions.append({"reference": reference, "action": "reject", "reviewer": REVIEWER})
    return resume_close(graph, config, decisions)


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_the_pack_is_the_six_files(final: dict):
    assert tuple(pack_files(final, DATA_DIR)) == PACK_FILES


def test_run_json_says_who_when_under_what_policy_from_what_code_and_inputs(final: dict, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "abc123")

    run = json.loads(pack_files(final, DATA_DIR)["run.json"])

    assert run["prepared_by"] == PREPARER
    assert run["reviewers"] == sorted({PREPARER, REVIEWER})
    assert run["policy"]["source"] == "built-in defaults"
    assert run["policy"]["materiality_threshold"] == "5000.00"
    assert run["code_version"] == "abc123"
    assert run["inputs"] == [
        {"file": str(DATA_DIR / name), "sha256": hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()}
        for name in ("entities.csv", "trial_balance.csv", "ic_ledger.csv")
    ]
    assert run["counts"] == {
        "ic_transaction_legs": 53,
        "entities_not_tying_out": 1,
        "clean_pairs": 11,
        "exceptions": 18,
        "decisions": 16,
        "eliminations": len(final["eliminations"]),
    }
    assert "synthetic" in run["note"]
    assert "not authenticated" in run["note"]


def test_every_exception_is_listed_with_its_decision_and_whether_it_was_booked(final: dict):
    rows = {row["reference"]: row for row in _rows(pack_files(final, DATA_DIR)["exceptions.csv"])}

    assert len(rows) == len(final["exceptions"]) == 18
    assert (rows[APPROVED]["decision"], rows[APPROVED]["reviewer"], rows[APPROVED]["booked"]) == (
        "approve",
        REVIEWER,
        "yes",
    )
    refused = rows[BY_THE_PREPARER]
    assert (refused["decision"], refused["reviewer"], refused["booked"]) == ("approve", PREPARER, "no")
    auto = [row for row in rows.values() if row["triage_classification"] == "auto_resolvable"]
    assert auto and all(row["decision"] == "" and row["booked"] == "yes" for row in auto)
    assert all(row["triage_rationale"] for row in rows.values())


def test_every_decision_is_listed_with_its_reviewer_and_time(final: dict):
    rows = _rows(pack_files(final, DATA_DIR)["decisions.csv"])

    assert [(r["reference"], r["action"], r["reviewer"]) for r in rows] == [
        (d.reference, d.action.value, d.reviewer) for d in final["review_decisions"]
    ]
    assert all(r["decided_at"].endswith("Z") for r in rows)


def test_the_journal_lines_are_the_entries_booked_and_each_balances(final: dict):
    rows = _rows(pack_files(final, DATA_DIR)["eliminations.csv"])

    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        totals[row["reference"]][row["line_type"]] += Decimal(row["amount"])
    assert list(totals) == [e.reference for e in final["eliminations"]]
    assert all(sides["debit"] == sides["credit"] > 0 for sides in totals.values())


def test_the_tieout_and_the_audit_trail_are_the_runs_own(final: dict):
    files = pack_files(final, DATA_DIR)

    tieout = {row["entity_code"]: row["within_tolerance"] for row in _rows(files["tieout.csv"])}
    assert tieout == {v.entity_code: str(v.within_tolerance) for v in final["tb_variances"]}
    assert tieout["US01"] == "False"
    assert files["audit_trail.txt"].splitlines() == final["audit_trail"]


def test_a_run_waiting_for_review_has_no_pack_yet(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    entities, trial_balance, transactions = load_dataset(DATA_DIR)
    _, _, paused = run_close(transactions, trial_balance, entities, thread_id="test-paused", prepared_by=PREPARER)

    with pytest.raises(ValueError, match="hasn't finalized"):
        pack_files(paused, DATA_DIR)


def test_a_written_pack_is_never_overwritten_and_zips_whole(final: dict, tmp_path: Path):
    first = write_pack(final, tmp_path, DATA_DIR)
    second = write_pack(final, tmp_path, DATA_DIR)

    assert first != second
    assert sorted(p.name for p in first.iterdir()) == sorted(PACK_FILES)
    assert all(b"\r" not in p.read_bytes() for p in first.iterdir())
    with zipfile.ZipFile(io.BytesIO(zip_pack(first))) as archive:
        assert sorted(archive.namelist()) == sorted(f"{first.name}/{name}" for name in PACK_FILES)
        assert archive.read(f"{first.name}/run.json") == (first / "run.json").read_bytes()


def test_outside_a_git_checkout_the_code_version_says_so(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(evidence, "ROOT", tmp_path)

    assert evidence.code_version() == "unknown: not run from a git checkout"


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_a_cli_run_that_finalizes_writes_its_pack(tmp_path: Path, monkeypatch):
    """The sample always stops for review, so this is a two-entity group with
    one clean balance: nothing to review, and the close finalizes in one go."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    _write(
        data / "entities.csv",
        "code,name,region,local_currency,reporting_currency,interfaced\n"
        "US01,Group US,US,USD,USD,True\nDE01,Group DE,EMEA,EUR,USD,True\n",
    )
    _write(
        data / "trial_balance.csv",
        "entity_code,account_code,account_name,balance\n"
        "US01,1000-IC-REC,Intercompany Receivable,1000.00\nDE01,2000-IC-PAY,Intercompany Payable,-1000.00\n",
    )
    _write(
        data / "ic_ledger.csv",
        "entity_code,counterparty_code,reference,amount,currency,transaction_date,description\n"
        "US01,DE01,FEE-1,1000.00,USD,2025-09-15,Fee\nDE01,US01,FEE-1,-1000.00,USD,2025-09-15,Fee\n",
    )

    result = CliRunner().invoke(
        app,
        ["run", "--data-dir", str(data), "--prepared-by", PREPARER, "--evidence-dir", str(tmp_path / "evidence")],
    )

    assert result.exit_code == 0, result.output
    [folder] = (tmp_path / "evidence").iterdir()
    assert f"Evidence pack: {folder}" in result.output
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert (run["prepared_by"], run["reviewers"], run["counts"]["eliminations"]) == (PREPARER, [], 1)


def test_a_run_from_a_workbook_records_the_workbook_as_its_input(final: dict):
    template = DATA_DIR.parent.parent / "examples" / "close_template.xlsx"

    run = json.loads(pack_files(final, template)["run.json"])

    assert run["inputs"] == [{"file": str(template), "sha256": hashlib.sha256(template.read_bytes()).hexdigest()}]
