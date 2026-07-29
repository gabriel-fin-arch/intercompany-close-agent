"""End-to-end tests for the close pipeline graph, offline (no ANTHROPIC_API_KEY).

Exercises the real interrupt/resume cycle against LangGraph's checkpointer --
not mocked -- so these tests double as a guard against LangGraph API drift.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_ic_transactions, load_trial_balance
from intercompany_close_agent.models.exception import ExceptionType
from intercompany_close_agent.models.review import ReviewAction

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _load_real_data():
    entities_path = DATA_DIR / "entities.csv"
    import csv

    from intercompany_close_agent.models.entity import Entity

    with entities_path.open(encoding="utf-8") as fh:
        entities = [Entity(**row) for row in csv.DictReader(fh)]

    transactions = load_ic_transactions(DATA_DIR / "ic_ledger.csv")
    trial_balance = load_trial_balance(DATA_DIR / "trial_balance.csv")
    return entities, trial_balance, transactions


def test_run_pauses_for_human_review_on_real_dataset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()

    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-1")

    # the synthetic dataset has real missing-counterparty / counterparty-mismatch
    # exceptions in it, so this run should hit the interrupt
    assert "__interrupt__" in result
    pending = result["__interrupt__"][0].value["pending_review"]
    assert len(pending) > 0
    assert result["exceptions"]
    assert result["triage_results"]


def test_resume_with_decisions_produces_final_eliminations(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()

    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-2")
    assert "__interrupt__" in result

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value, "reviewer_note": "test approval"}
        for item in pending
    ]

    final = resume_close(graph, config, decisions)

    assert "__interrupt__" not in final
    assert "eliminations" in final
    assert len(final["eliminations"]) > 0
    assert any("finalized" in entry for entry in final["audit_trail"])


def test_rejecting_a_decision_excludes_it_from_eliminations(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()

    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-3")
    pending = result["__interrupt__"][0].value["pending_review"]

    # reject the first one, approve the rest
    decisions = []
    for i, item in enumerate(pending):
        action = ReviewAction.REJECT.value if i == 0 else ReviewAction.APPROVE.value
        decisions.append({"reference": item["reference"], "action": action, "reviewer_note": "test"})

    final = resume_close(graph, config, decisions)

    rejected_reference = pending[0]["reference"]
    eliminated_references = {e.reference for e in final["eliminations"]}
    assert rejected_reference not in eliminated_references


def test_approving_a_missing_counterparty_with_an_amount_books_it(monkeypatch):
    """A one-legged exception can only be booked if the reviewer supplies the amount."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-5")

    one_legged = {exc.reference for exc in result["exceptions"] if len(exc.legs) == 1}
    assert one_legged, "the synthetic dataset should contain at least one missing counterparty"
    target = sorted(one_legged)[0]

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = []
    for item in pending:
        if item["reference"] == target:
            decisions.append(
                {
                    "reference": target,
                    "action": ReviewAction.APPROVE.value,
                    "reviewer_note": "confirmed with the affiliate",
                    "override_amount": "5000.00",
                }
            )
        else:
            decisions.append({"reference": item["reference"], "action": ReviewAction.REJECT.value})

    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert target in booked

    elimination = next(e for e in final["eliminations"] if e.reference == target)
    assert all(line.amount == Decimal("5000.00") for line in elimination.lines)
    assert "confirmed with the affiliate" in elimination.narrative


def test_approving_a_missing_counterparty_without_an_amount_is_not_booked(monkeypatch):
    """Approval alone isn't enough when there's no amount to book."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-6")

    one_legged = {exc.reference for exc in result["exceptions"] if len(exc.legs) == 1}
    target = sorted(one_legged)[0]

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value}
        for item in pending
    ]

    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert target not in booked
    # and the audit trail says why, rather than the item silently vanishing
    assert any(target in entry and "not booked automatically" in entry for entry in final["audit_trail"])


def test_missing_counterparty_never_auto_resolves(monkeypatch):
    """Sanity check on the taxonomy: a missing-counterparty exception in the
    real dataset should always show up in pending_review, never be silently
    auto-eliminated."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-4")

    missing_counterparty_refs = {
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.MISSING_COUNTERPARTY
    }
    if missing_counterparty_refs:
        pending_refs = {item["reference"] for item in result["__interrupt__"][0].value["pending_review"]}
        assert missing_counterparty_refs.issubset(pending_refs)
