"""Deterministic, rule-based triage fallback.

Used whenever no Anthropic API key or model is configured, so the whole
pipeline can run fully offline -- no network call, no missing-key crash,
just a plainer rationale than a live model would write. The classification
logic is deliberately simple and legible: it's the fallback path, and a
fallback that's hard to reason about defeats the point of having one.
"""

from __future__ import annotations

from intercompany_close_agent.models.entity import Entity
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
    # Two legs in different currencies can't be netted without an FX rate,
    # and FX translation is out of scope here -- so there is nothing to
    # auto-resolve, only someone to tell.
    ExceptionType.CURRENCY_MISMATCH,
}

# Confidence penalty applied when a non-interfaced (manually loaded) entity
# is on either side of the balance. Their data has been keyed in by hand, so
# an otherwise-immaterial residual is less likely to mean what it looks like.
# REVIEW: the size of this penalty is a judgment call, not a standard.
MANUAL_ENTITY_CONFIDENCE_PENALTY = 0.15

# Below this confidence, an otherwise auto-resolvable exception gets escalated
# instead. Keeps the "how sure are we" and "who decides" questions connected.
AUTO_RESOLVE_MIN_CONFIDENCE = 0.6


def _manual_entities(exc: ICException, entities: dict[str, Entity] | None) -> list[str]:
    """Entity codes on this exception that don't load through a system interface."""
    if not entities:
        return []
    return sorted(
        code
        for code in exc.involved_entity_codes
        if code in entities and not entities[code].interfaced
    )


def triage_exception(exc: ICException, entities: dict[str, Entity] | None = None) -> TriageResult:
    manual = _manual_entities(exc, entities)

    if exc.exception_type in _ALWAYS_NEEDS_JUDGMENT:
        rationale = (
            f"{exc.exception_type.value.replace('_', ' ')} exceptions are never auto-resolved "
            f"by the rule fallback: {exc.detected_reason}"
        )
        if manual:
            rationale = (
                f"{rationale} Worth checking the manual load first -- "
                f"{', '.join(manual)} keys its data in by hand."
            )
        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
            confidence=0.95,
            rationale=rationale,
        )

    # AMOUNT_MISMATCH / TIMING_GAP -- these are genuine intercompany balances
    # on both sides that just didn't line up cleanly. Materiality decides
    # whether that's worth a human's time.
    if exc.materiality == Materiality.LOW:
        confidence = 0.7
        rationale = (
            f"{exc.detected_reason} Residual is below the group materiality threshold, "
            f"proposed for auto-elimination rather than escalation."
        )

        if manual:
            confidence -= MANUAL_ENTITY_CONFIDENCE_PENALTY
            rationale = (
                f"{rationale} Confidence reduced because {', '.join(manual)} "
                f"{'loads' if len(manual) == 1 else 'load'} manually rather than through a "
                f"system interface."
            )

        if confidence < AUTO_RESOLVE_MIN_CONFIDENCE:
            return TriageResult(
                reference=exc.reference,
                classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
                confidence=confidence,
                rationale=f"{rationale} Escalating rather than auto-eliminating at this confidence.",
            )

        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.AUTO_RESOLVABLE,
            confidence=confidence,
            rationale=rationale,
        )

    confidence = 0.8 - (MANUAL_ENTITY_CONFIDENCE_PENALTY if manual else 0.0)
    rationale = f"{exc.detected_reason} Residual is material, so this needs sign-off before eliminating."
    if manual:
        rationale = f"{rationale} Note that {', '.join(manual)} is a manually loaded entity."

    return TriageResult(
        reference=exc.reference,
        classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
        confidence=confidence,
        rationale=rationale,
    )
