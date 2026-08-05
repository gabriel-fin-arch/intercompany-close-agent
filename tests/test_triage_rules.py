"""Tests for the offline, rule-based triage fallback."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.triage.models import TriageClassification
from intercompany_close_agent.triage.rules import triage_exception


def _leg(entity: str, counterparty: str, reference: str, amount: str) -> ICTransaction:
    return ICTransaction(
        entity_code=entity,
        counterparty_code=counterparty,
        reference=reference,
        amount=Decimal(amount),
        transaction_date=date(2025, 9, 30),
    )


def _exc(exception_type: ExceptionType, materiality: Materiality, reference: str = "REF-1") -> ICException:
    return ICException(
        reference=reference,
        exception_type=exception_type,
        legs=[_leg("US01", "DE01", reference, "100.00"), _leg("DE01", "US01", reference, "-90.00")],
        net_amount=Decimal("10.00"),
        materiality=materiality,
        detected_reason="test fixture",
    )


def test_missing_counterparty_always_needs_judgment():
    result = triage_exception(_exc(ExceptionType.MISSING_COUNTERPARTY, Materiality.LOW))
    assert result.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT


def test_counterparty_mismatch_always_needs_judgment_even_if_low_materiality():
    result = triage_exception(_exc(ExceptionType.COUNTERPARTY_MISMATCH, Materiality.LOW))
    assert result.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT


def test_duplicate_reference_always_needs_judgment():
    result = triage_exception(_exc(ExceptionType.DUPLICATE_REFERENCE, Materiality.LOW))
    assert result.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT


def test_low_materiality_amount_mismatch_is_auto_resolvable():
    result = triage_exception(_exc(ExceptionType.AMOUNT_MISMATCH, Materiality.LOW))
    assert result.classification == TriageClassification.AUTO_RESOLVABLE


def test_high_materiality_amount_mismatch_needs_judgment():
    result = triage_exception(_exc(ExceptionType.AMOUNT_MISMATCH, Materiality.HIGH))
    assert result.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT


def test_low_materiality_timing_gap_is_auto_resolvable():
    result = triage_exception(_exc(ExceptionType.TIMING_GAP, Materiality.LOW))
    assert result.classification == TriageClassification.AUTO_RESOLVABLE


def test_result_keeps_the_exception_reference():
    result = triage_exception(_exc(ExceptionType.AMOUNT_MISMATCH, Materiality.LOW, reference="REF-XYZ"))
    assert result.reference == "REF-XYZ"
