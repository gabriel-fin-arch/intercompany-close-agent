"""Deterministic, rule-based triage fallback.

Used whenever no Anthropic API key or model is configured, so the whole
pipeline can run fully offline -- no network call, no missing-key crash,
just a plainer rationale than a live model would write. The classification
logic is deliberately simple and legible: it's the fallback path, and a
fallback that's hard to reason about defeats the point of having one.
"""

from __future__ import annotations

from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.triage.models import TriageClassification, TriageResult

# Exception types where there's genuinely nothing to auto-resolve: a missing
# booking, an ambiguous duplicate, or a balance that landed on the wrong
# entity are control questions, not amount questions. No rule engine should
# paper over those on its own, no matter how small the dollar amount.
# REVIEW: this taxonomy reflects one reasonable read of what "needs a
# human" means for an IC close -- validate it against your own group's
# risk appetite before relying on it.
_ALWAYS_NEEDS_JUDGMENT = {
    ExceptionType.MISSING_COUNTERPARTY,
    ExceptionType.DUPLICATE_REFERENCE,
    ExceptionType.COUNTERPARTY_MISMATCH,
}


def triage_exception(exc: ICException) -> TriageResult:
    if exc.exception_type in _ALWAYS_NEEDS_JUDGMENT:
        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
            confidence=0.95,
            rationale=(
                f"{exc.exception_type.value.replace('_', ' ')} exceptions are never auto-resolved "
                f"by the rule fallback: {exc.detected_reason}"
            ),
        )

    # AMOUNT_MISMATCH / TIMING_GAP -- these are genuine intercompany balances
    # on both sides that just didn't line up cleanly. Materiality decides
    # whether that's worth a human's time.
    if exc.materiality == Materiality.LOW:
        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.AUTO_RESOLVABLE,
            confidence=0.7,
            rationale=(
                f"{exc.detected_reason} Residual is below the group materiality threshold, "
                f"proposed for auto-elimination rather than escalation."
            ),
        )

    return TriageResult(
        reference=exc.reference,
        classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
        confidence=0.8,
        rationale=f"{exc.detected_reason} Residual is material, so this needs sign-off before eliminating.",
    )
