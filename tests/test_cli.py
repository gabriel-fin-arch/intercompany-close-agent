"""Tests for the CLI commands, run offline (no ANTHROPIC_API_KEY)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from intercompany_close_agent.cli import app

runner = CliRunner()


def test_generate_data_writes_csvs(tmp_path: Path):
    out_dir = tmp_path / "synthetic"
    result = runner.invoke(app, ["generate-data", "--seed", "7", "--pairs", "10", "--out-dir", str(out_dir)])

    assert result.exit_code == 0
    assert (out_dir / "entities.csv").exists()
    assert (out_dir / "trial_balance.csv").exists()
    assert (out_dir / "ic_ledger.csv").exists()


def test_run_against_generated_data_offline(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    data_dir = tmp_path / "synthetic"
    gen_result = runner.invoke(app, ["generate-data", "--seed", "7", "--pairs", "10", "--out-dir", str(data_dir)])
    assert gen_result.exit_code == 0

    run_result = runner.invoke(app, ["run", "--data-dir", str(data_dir)])

    assert run_result.exit_code == 0
    assert "Triage mode: offline rule-based fallback" in run_result.output
    assert "Audit trail" in run_result.output


def test_run_against_committed_sample_dataset():
    """Run against the real data/synthetic/*.csv shipped in the repo."""
    data_dir = Path(__file__).resolve().parent.parent / "data" / "synthetic"
    result = runner.invoke(app, ["run", "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    assert "ingested" in result.output
    assert "matched" in result.output
