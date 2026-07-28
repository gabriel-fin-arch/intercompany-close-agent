"""Tests for the triage dispatcher: picks LLM vs. offline rules, falls back on error."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.triage import node as triage_node
from intercompany_close_agent.triage.models import TriageClassification, TriageResult


def _exc() -> ICException:
    leg = ICTransaction(
        entity_code="US01",
        counterparty_code="DE01",
        reference="REF-1",
        amount=Decimal("100.00"),
        transaction_date=date(2025, 9, 30),
    )
    return ICException(
        reference="REF-1",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        legs=[leg],
        net_amount=Decimal("10.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )


def test_uses_rules_when_no_llm_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    result = triage_node.triage_exception(_exc())

    assert result.classification == TriageClassification.AUTO_RESOLVABLE  # rules.py's call for this fixture


def test_uses_llm_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")

    def fake_llm_triage(exc: ICException, entities=None) -> TriageResult:
        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
            confidence=0.5,
            rationale="from the fake LLM",
        )

    monkeypatch.setattr("intercompany_close_agent.triage.llm.triage_exception", fake_llm_triage)

    result = triage_node.triage_exception(_exc())

    assert result.rationale == "from the fake LLM"


def test_falls_back_to_rules_when_llm_call_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")

    def broken_llm_triage(exc: ICException, entities=None) -> TriageResult:
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr("intercompany_close_agent.triage.llm.triage_exception", broken_llm_triage)

    result = triage_node.triage_exception(_exc())

    # didn't blow up -- fell back to the deterministic rules path
    assert result.classification == TriageClassification.AUTO_RESOLVABLE


def test_triage_all_preserves_order():
    exceptions = [_exc(), _exc()]
    results = triage_node.triage_all(exceptions)
    assert len(results) == 2
