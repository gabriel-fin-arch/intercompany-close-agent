"""Tests for the parts of the LLM triage module that don't require a live call."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.triage.llm import _build_chain, _describe, triage_exception
from intercompany_close_agent.triage.models import TriageClassification, TriageJudgment


def _exc() -> ICException:
    legs = [
        ICTransaction(
            entity_code="US01",
            counterparty_code="DE01",
            reference="REF-1",
            amount=Decimal("1000.00"),
            transaction_date=date(2025, 9, 30),
        ),
        ICTransaction(
            entity_code="DE01",
            counterparty_code="US01",
            reference="REF-1",
            amount=Decimal("-950.00"),
            transaction_date=date(2025, 9, 30),
        ),
    ]
    return ICException(
        reference="REF-1",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        legs=legs,
        net_amount=Decimal("50.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )


def test_describe_includes_the_key_facts():
    description = _describe(_exc())
    assert "REF-1" in description
    assert "amount_mismatch" in description
    assert "US01" in description
    assert "DE01" in description


def test_describe_flags_a_manually_loaded_entity():
    entities = {
        "US01": Entity(code="US01", name="US", region="US", local_currency="USD", interfaced=True),
        "DE01": Entity(code="DE01", name="DE", region="EMEA", local_currency="EUR", interfaced=False),
    }
    description = _describe(_exc(), entities)
    assert "manually_loaded_entities: DE01" in description


def test_build_chain_requires_a_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_MODEL"):
        _build_chain()


def test_build_chain_constructs_a_runnable_chain(monkeypatch):
    """The prompt/model/parser wiring is built without ever calling the API."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "some-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")

    chain = _build_chain()

    assert hasattr(chain, "invoke")


def test_triage_exception_maps_the_model_judgment_onto_the_reference(monkeypatch):
    """Exercises the real function body with a stubbed chain, so the LLM path
    is covered end to end without a network call."""
    captured = {}

    class FakeChain:
        def invoke(self, payload):
            captured["payload"] = payload
            return TriageJudgment(
                classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
                confidence=0.42,
                rationale="model says look at this one",
            )

    monkeypatch.setattr("intercompany_close_agent.triage.llm._build_chain", lambda: FakeChain())

    result = triage_exception(_exc())

    assert result.reference == "REF-1"  # set by our code, not echoed by the model
    assert result.confidence == 0.42
    assert result.rationale == "model says look at this one"
    assert "amount_mismatch" in captured["payload"]["exception_details"]


def test_triage_exception_accepts_a_plain_dict_from_the_model(monkeypatch):
    """Structured output can come back as a dict rather than a model instance."""

    class DictChain:
        def invoke(self, payload):
            return {
                "classification": "auto_resolvable",
                "confidence": 0.9,
                "rationale": "immaterial",
            }

    monkeypatch.setattr("intercompany_close_agent.triage.llm._build_chain", lambda: DictChain())

    result = triage_exception(_exc())

    assert result.classification == TriageClassification.AUTO_RESOLVABLE
    assert result.reference == "REF-1"
