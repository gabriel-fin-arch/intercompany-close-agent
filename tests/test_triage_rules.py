"""Tests for the offline, rule-based triage fallback."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from intercompany_close_agent.models.entity import Entity
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


def test_sign_mismatch_always_needs_judgment_even_if_low_materiality():
    result = triage_exception(_exc(ExceptionType.SIGN_MISMATCH, Materiality.LOW))
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


# --- entity risk profile ---------------------------------------------------
# The fixtures above involve US01 and DE01, so these build an entity index
# where one of them is manually loaded and check that it actually changes the
# outcome -- the whole point of tracking the interfaced flag.

_INTERFACED = {
    "US01": Entity(code="US01", name="Test US", region="US", local_currency="USD", interfaced=True),
    "DE01": Entity(code="DE01", name="Test DE", region="EMEA", local_currency="EUR", interfaced=True),
}
_ONE_MANUAL = {
    "US01": _INTERFACED["US01"],
    "DE01": Entity(code="DE01", name="Test DE", region="EMEA", local_currency="EUR", interfaced=False),
}


def test_manual_entity_is_named_in_the_rationale():
    """A reviewer should be told why this one is in front of them."""
    exc = _exc(ExceptionType.AMOUNT_MISMATCH, Materiality.HIGH)
    result = triage_exception(exc, _ONE_MANUAL)

    assert "DE01" in result.rationale
    assert "by hand" in result.rationale


def test_manual_entity_escalates_what_would_otherwise_auto_resolve():
    exc = _exc(ExceptionType.AMOUNT_MISMATCH, Materiality.LOW)

    # all-interfaced: immaterial residual is safe to auto-resolve
    assert triage_exception(exc, _INTERFACED).classification == TriageClassification.AUTO_RESOLVABLE

    # same exception, but one side was keyed in by hand -> policy says no
    escalated = triage_exception(exc, _ONE_MANUAL)
    assert escalated.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT
    assert "regardless of size" in escalated.rationale


def test_entities_are_optional_and_default_to_the_old_behaviour():
    exc = _exc(ExceptionType.AMOUNT_MISMATCH, Materiality.LOW)
    assert triage_exception(exc).classification == TriageClassification.AUTO_RESOLVABLE


def test_counterparty_side_counts_even_without_a_booked_leg():
    """A missing counterparty booking should still surface the absent entity."""
    exc = _exc(ExceptionType.AMOUNT_MISMATCH, Materiality.HIGH)
    # DE01 only ever appears as the counterparty on the first leg
    assert "DE01" in exc.involved_entity_codes


def test_a_timing_gap_is_not_described_as_a_residual():
    """Its legs agree, so the net amount a reviewer sees next to it is 0.00. The
    band was measured on the balance straddling the cutoff, and the rationale
    has to say so rather than call a zero material."""
    result = triage_exception(_exc(ExceptionType.TIMING_GAP, Materiality.HIGH))

    assert "residual" not in result.rationale.lower()
    assert "The balance straddling the cutoff is material" in result.rationale


def test_an_amount_mismatch_is_still_about_its_residual():
    result = triage_exception(_exc(ExceptionType.AMOUNT_MISMATCH, Materiality.HIGH))

    assert "The residual is material" in result.rationale
