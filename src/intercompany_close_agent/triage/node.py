"""Picks the LLM-backed or offline rule-based triage implementation.

This is the one place in the codebase that decides which triage path runs,
and the one place that enforces the taxonomy on the way out. Whichever
implementation produced the result, the caller gets back the same
TriageResult shape and the same guarantees; the graph node, the CLI and the
dashboard never need to know which one ran.
"""

from __future__ import annotations

import os

from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.triage.models import TriageClassification, TriageResult
from intercompany_close_agent.triage.rules import ALWAYS_NEEDS_JUDGMENT


def _llm_is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(os.environ.get("ANTHROPIC_MODEL"))


def _enforce_taxonomy(exc: ICException, result: TriageResult) -> TriageResult:
    """Hold the never-auto-resolve rule in code, whatever the classifier said.

    The system prompt tells the model this rule, but a prompt is a request,
    not a guarantee. Free text from the ledger (an intercompany reference is
    typed by whoever submitted the balance) ends up inside that prompt, so a
    reference carrying an instruction could talk a model into returning
    auto_resolvable for an exception that must never be auto-resolved. The
    cost of that would be an unreviewed elimination.

    So the rule is enforced here as well, on the way out, where no prompt can
    reach it. If the model disagrees with the taxonomy, the taxonomy wins and
    the override is recorded in the rationale the reviewer reads.
    """
    if exc.exception_type not in ALWAYS_NEEDS_JUDGMENT:
        return result
    if result.classification == TriageClassification.NEEDS_HUMAN_JUDGMENT:
        return result

    return result.model_copy(
        update={
            "classification": TriageClassification.NEEDS_HUMAN_JUDGMENT,
            "rationale": (
                f"[overridden] The classifier returned auto_resolvable, but "
                f"{exc.exception_type.value.replace('_', ' ')} exceptions are never "
                f"auto-resolved. Original rationale: {result.rationale}"
            ),
        }
    )


def triage_exception(exc: ICException, entities: dict[str, Entity] | None = None) -> TriageResult:
    if _llm_is_configured():
        from intercompany_close_agent.triage.llm import triage_exception as llm_triage

        try:
            return _enforce_taxonomy(exc, llm_triage(exc, entities))
        except Exception:
            # A live model call can fail for all sorts of reasons: rate
            # limit, network blip, an unexpected response shape. Falling
            # back to the deterministic rules keeps the close moving
            # instead of taking the whole run down over one exception.
            from intercompany_close_agent.triage.rules import triage_exception as rules_triage

            return _enforce_taxonomy(exc, rules_triage(exc, entities))

    from intercompany_close_agent.triage.rules import triage_exception as rules_triage

    return _enforce_taxonomy(exc, rules_triage(exc, entities))


def triage_all(
    exceptions: list[ICException], entities: dict[str, Entity] | None = None
) -> list[TriageResult]:
    return [triage_exception(exc, entities) for exc in exceptions]
