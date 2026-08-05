"""Tests for the parts of the LLM triage module that don't require a live call."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.triage.llm import _build_chain, _describe


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


def test_build_chain_requires_a_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_MODEL"):
        _build_chain()
