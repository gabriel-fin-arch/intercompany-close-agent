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
ALWAYS_NEEDS_JUDGMENT = {
    ExceptionType.MISSING_COUNTERPARTY,
    ExceptionType.DUPLICATE_REFERENCE,
    ExceptionType.COUNTERPARTY_MISMATCH,
    # An entity booked as its own counterparty is a data error upstream, not
    # a balance to eliminate -- someone has to go fix the mapping.
    ExceptionType.SELF_DEALING,
    # Two legs in different currencies can't be netted without an FX rate,
    # and FX translation is out of scope here -- so there is nothing to
    # auto-resolve, only someone to tell.
    ExceptionType.CURRENCY_MISMATCH,
}

# Confidence bands for the deterministic path. These are fixed labels, not
# probabilities -- a rule engine has no distribution to draw one from, and
# dressing a policy decision up as 0.83 would be false precision. They exist
# so the rule path and the model path hand back the same shape, and so a
# reviewer sorting a worklist gets a sensible order either way.
CONFIDENCE_POLICY = 0.95  # a stated rule fired; nothing was weighed
CONFIDENCE_MATERIAL = 0.80  # judgment call, but the amount makes it clear-cut
CONFIDENCE_IMMATERIAL = 0.70  # judgment call on a small residual


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

    if exc.exception_type in ALWAYS_NEEDS_JUDGMENT:
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
            confidence=CONFIDENCE_POLICY,
            rationale=rationale,
        )

    # AMOUNT_MISMATCH / TIMING_GAP -- genuine intercompany balances on both
    # sides that just didn't line up cleanly. Two things decide whether a
    # human needs to see it: how big the residual is, and how much the data
    # underneath it can be trusted.
    if manual:
        # A manually keyed balance doesn't get auto-eliminated on the strength
        # of being small. This is a policy, stated once, rather than a
        # confidence penalty tuned until it happened to cross a threshold --
        # the outcome is the same and the reasoning survives being asked about.
        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
            confidence=CONFIDENCE_POLICY,
            rationale=(
                f"{exc.detected_reason} Not auto-eliminated regardless of size: "
                f"{', '.join(manual)} "
                f"{'keys' if len(manual) == 1 else 'key'} data in by hand rather than "
                f"loading through a system interface."
            ),
        )

    if exc.materiality == Materiality.LOW:
        return TriageResult(
            reference=exc.reference,
            classification=TriageClassification.AUTO_RESOLVABLE,
            confidence=CONFIDENCE_IMMATERIAL,
            rationale=(
                f"{exc.detected_reason} Residual is below the group materiality threshold and "
                f"both sides load through a system interface, so it's proposed for "
                f"auto-elimination rather than escalation."
            ),
        )

    return TriageResult(
        reference=exc.reference,
        classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
        confidence=CONFIDENCE_MATERIAL,
        rationale=(
            f"{exc.detected_reason} Residual is material, so this needs sign-off before eliminating."
        ),
    )
