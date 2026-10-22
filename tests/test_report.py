"""The static report CI publishes: offline, about synthetic data, and consistent
with the run it reports."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from intercompany_close_agent.cli import app
from intercompany_close_agent.report import REPO, build, render
from intercompany_close_agent.sample_results import summary_of


def test_the_report_is_the_offline_run_whatever_the_environment_says(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5-5")

    def no_model_calls(*args, **kwargs):
        raise AssertionError("the report called the model")

    monkeypatch.setattr("intercompany_close_agent.triage.llm.triage_exception", no_model_calls)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    result = CliRunner().invoke(app, ["report", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Synthetic data" in page
    assert "no model was called" in page
    assert f'href="{REPO}"' in page


def test_the_report_counts_what_the_run_found():
    report = build()
    summary = summary_of(report.entities, report.transactions, report.paused)
    page = render(report)

    assert f"Reviewer worklist ({summary.for_review})" in page
    assert f"Proposed for auto-elimination ({summary.auto_resolvable})" in page
    assert f"Pairs that matched clean ({summary.clean_pairs})" in page
    # Before any decision, finalize books the clean pairs and the auto-resolved
    # exceptions, and nothing from the worklist.
    booked = len(report.final["eliminations"])
    assert booked == summary.clean_pairs + summary.auto_resolvable
    assert f"Eliminations booked before any review ({booked})" in page
    assert page.count("does not tie") == summary.entities_not_tying


def test_the_report_links_the_commit_it_was_built_from():
    page = render(build(), commit="0123456789abcdef")

    assert f'href="{REPO}/commit/0123456789abcdef"' in page
    assert "<code>0123456</code>" in page
