"""Tests for the close at the size of a real group, and the doc that quotes it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from intercompany_close_agent.cli import app
from intercompany_close_agent.scale import _offline, report, scale_run
from intercompany_close_agent.synthetic.generator import ENTITIES, entities_for

DOC = Path(__file__).resolve().parent.parent / "docs" / "scale.md"


@pytest.fixture(scope="module")
def default_run():
    return scale_run()


def test_a_60_entity_group_closes_with_the_counts_its_seed_gives(default_run):
    assert (
        default_run.entities,
        default_run.balances,
        default_run.ledger_lines,
        default_run.clean_pairs,
        default_run.exceptions,
        default_run.for_review,
        default_run.not_tying_out,
        default_run.eliminations,
    ) == (60, 1500, 3005, 1440, 76, 68, 1, 1448)


def test_what_is_booked_is_the_clean_pairs_and_what_triage_auto_resolved(default_run):
    auto_resolved = default_run.exceptions - default_run.for_review

    assert default_run.eliminations == default_run.clean_pairs + auto_resolved


def test_the_doc_quotes_the_counts_a_fresh_run_gives(default_run):
    """The times in docs/scale.md are one run on one machine; the counts are
    not, and they have to match what the command prints today."""
    doc = DOC.read_text(encoding="utf-8")

    for line in report(default_run, seed=14, anomaly_rate=0.05)[:3]:
        assert f"\n{line}\n" in doc, line


def test_the_command_prints_counts_then_time_then_machine():
    result = CliRunner().invoke(app, ["scale-run", "--entities", "10", "--pairs", "40"])

    assert result.exit_code == 0, result.output
    labels = [line.split(":")[0] for line in result.output.splitlines()]
    assert labels == ["Group", "Found", "Booked", "Time", "Machine", "Offline"]
    assert result.output.startswith("Group: 10 entities, 40 balances")


def test_the_run_is_offline_whatever_the_environment_holds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "not-a-real-model")

    with _offline():
        assert "ANTHROPIC_API_KEY" not in os.environ
        assert "ANTHROPIC_MODEL" not in os.environ

    assert os.environ["ANTHROPIC_API_KEY"] == "not-a-real-key"
    assert os.environ["ANTHROPIC_MODEL"] == "not-a-real-model"


def test_a_larger_group_keeps_the_sample_entities_and_adds_interfaced_ones():
    group = entities_for(60)

    assert entities_for(len(ENTITIES)) == ENTITIES
    assert group[: len(ENTITIES)] == ENTITIES
    assert len({entity.code for entity in group}) == 60
    assert [entity.code for entity in group if not entity.interfaced] == ["ZA01"]


def test_a_group_smaller_than_the_sample_is_refused():
    with pytest.raises(ValueError, match="at least the sample's 7 entities"):
        entities_for(5)
