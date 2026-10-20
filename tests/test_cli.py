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


def test_every_command_prints_its_help():
    """Below typer 0.16, --help goes through a click API that changed in 8.2 and
    dies with a traceback. Nothing else in this file asks for help, so the suite
    stayed green on a floor that could not print a usage line."""
    for command in ([], ["run"], ["generate-data"]):
        result = runner.invoke(app, [*command, "--help"])

        assert result.exit_code == 0, result.output
        assert "Usage" in result.output


def test_run_with_missing_data_dir_fails_loudly(tmp_path: Path):
    """A bad --data-dir should error out, not silently produce an empty run."""
    missing_dir = tmp_path / "does-not-exist"
    result = runner.invoke(app, ["run", "--data-dir", str(missing_dir)])

    assert result.exit_code == 1
    assert "not found" in result.output
    assert "Traceback" not in result.output


def test_run_refuses_a_ledger_with_nothing_in_it(tmp_path: Path):
    data_dir = tmp_path / "synthetic"
    runner.invoke(app, ["generate-data", "--out-dir", str(data_dir)])
    header = (data_dir / "ic_ledger.csv").read_text(encoding="utf-8").splitlines()[0]
    (data_dir / "ic_ledger.csv").write_text(header + "\n", encoding="utf-8")

    result = runner.invoke(app, ["run", "--data-dir", str(data_dir)])

    assert result.exit_code == 1
    assert "nothing to close" in result.output
    assert "No items needed human review" not in result.output


def test_run_against_committed_sample_dataset():
    """Run against the real data/synthetic/*.csv shipped in the repo."""
    data_dir = Path(__file__).resolve().parent.parent / "data" / "synthetic"
    result = runner.invoke(app, ["run", "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    assert "ingested" in result.output
    assert "matched" in result.output


SAMPLE = Path(__file__).resolve().parent.parent / "data" / "synthetic"
EXAMPLE_POLICY = Path(__file__).resolve().parent.parent / "examples" / "policy.toml"


def test_run_records_who_prepared_it_and_the_policy_it_used(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    result = runner.invoke(
        app,
        ["run", "--data-dir", str(SAMPLE), "--policy", str(EXAMPLE_POLICY), "--prepared-by", "Ana Ruiz"],
    )

    assert result.exit_code == 0, result.output
    assert "  - prepared by Ana Ruiz" in result.output
    assert f"  - policy ({EXAMPLE_POLICY}): materiality threshold 5000.00;" in result.output


def test_run_without_prepared_by_records_the_login_name(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setattr("getpass.getuser", lambda: "aruiz")

    result = runner.invoke(app, ["run", "--data-dir", str(SAMPLE)])

    assert result.exit_code == 0, result.output
    assert "  - prepared by aruiz" in result.output
    assert "  - policy (built-in defaults):" in result.output


def test_run_refuses_a_policy_it_cannot_use(tmp_path: Path):
    policy = tmp_path / "policy.toml"
    policy.write_text("materiality_threshold = -5\n", encoding="utf-8")

    result = runner.invoke(app, ["run", "--data-dir", str(SAMPLE), "--policy", str(policy)])

    assert result.exit_code == 1
    assert "Cannot run the close:" in result.output
    assert "materiality_threshold" in result.output
    assert "Traceback" not in result.output


def test_run_refuses_a_blank_preparer():
    result = runner.invoke(app, ["run", "--data-dir", str(SAMPLE), "--prepared-by", "  "])

    assert result.exit_code == 1
    assert "--prepared-by can't be blank" in result.output
