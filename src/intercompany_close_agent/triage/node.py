"""Picks the LLM-backed or offline rule-based triage implementation.

This is the one place in the codebase that decides which triage path runs,
and the one place that enforces the auto-resolve policy on the way out.
Whichever implementation produced the result, the caller gets back the same
TriageResult shape and the same guarantees; the graph node, the CLI and the
dashboard never need to know which one ran.
"""

from __future__ import annotations

import os

from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ICException, Materiality
from intercompany_close_agent.triage.models import TriageClassification, TriageResult
from intercompany_close_agent.triage.rules import ALWAYS_NEEDS_JUDGMENT


def _llm_is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(os.environ.get("ANTHROPIC_MODEL"))


def _manual_entities(exc: ICException, entities: dict[str, Entity] | None) -> list[str]:
    """Entity codes on this exception that don't load through a system interface."""
    if not entities:
        return []
    return sorted(
        code
        for code in exc.involved_entity_codes
        if code in entities and not entities[code].interfaced
    )


def _override(result: TriageResult, reason: str) -> TriageResult:
    return result.model_copy(
        update={
            "classification": TriageClassification.NEEDS_HUMAN_JUDGMENT,
            "rationale": f"[overridden] The classifier returned auto_resolvable, but {reason}. "
            f"Original rationale: {result.rationale}",
        }
    )


def _enforce_taxonomy(
    exc: ICException, result: TriageResult, entities: dict[str, Entity] | None = None
) -> TriageResult:
    """Hold the whole auto-resolve policy in code, whatever the classifier said.

    Three things gate auto-resolution, and none of them are optional just
    because a live model call said otherwise: the exception type isn't one
    of the six that are never auto-resolved, the residual is immaterial,
    and no entity on either side of the balance is manually loaded. All
    three are also stated in the system prompt in `triage/llm.py` -- but a
    prompt is a request, not a guarantee. Free text from the ledger (an
    intercompany reference is typed by whoever submitted the balance) ends
    up inside that prompt, so a reference carrying an instruction, or a
    model that's simply wrong about the materiality or the entity's data
    quality, could return auto_resolvable for something that must never be.
    The cost of that would be an unreviewed elimination.

    So the policy is re-applied here as well, on the way out, where no
    prompt can reach it. If the classifier disagrees with any part of it,
    the policy wins and the override is recorded in the rationale the
    reviewer reads, alongside what the classifier originally said.
    """
    if result.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT:
        return result

    if exc.exception_type in ALWAYS_NEEDS_JUDGMENT:
        return _override(
            result,
            f"{exc.exception_type.value.replace('_', ' ')} exceptions are never auto-resolved",
        )

    if exc.materiality == Materiality.HIGH:
        return _override(result, "the residual is above the group materiality threshold")

    manual = _manual_entities(exc, entities)
    if manual:
        verb = "keys" if len(manual) == 1 else "key"
        return _override(
            result,
            f"{', '.join(manual)} {verb} data in by hand rather than loading through a system "
            f"interface, so this isn't auto-eliminated regardless of size",
        )

    return result


def triage_exception(exc: ICException, entities: dict[str, Entity] | None = None) -> TriageResult:
    if _llm_is_configured():
        from intercompany_close_agent.triage.llm import triage_exception as llm_triage

        try:
            return _enforce_taxonomy(exc, llm_triage(exc, entities), entities)
        except Exception:
            # A live model call can fail for all sorts of reasons: rate
            # limit, network blip, an unexpected response shape. Falling
            # back to the deterministic rules keeps the close moving
            # instead of taking the whole run down over one exception.
            from intercompany_close_agent.triage.rules import triage_exception as rules_triage

            return _enforce_taxonomy(exc, rules_triage(exc, entities), entities)

    from intercompany_close_agent.triage.rules import triage_exception as rules_triage

    return _enforce_taxonomy(exc, rules_triage(exc, entities), entities)


def triage_all(
    exceptions: list[ICException], entities: dict[str, Entity] | None = None
) -> list[TriageResult]:
    return [triage_exception(exc, entities) for exc in exceptions]
