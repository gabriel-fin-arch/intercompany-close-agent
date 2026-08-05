"""Node functions for the intercompany close graph.

Each node is a small function of state -> partial state update. Only one of
them talks to the outside world (triage, which may call a live Claude
model); everything else is the same deterministic code already covered by
the matching/ and eliminations/ unit tests. human_review is the one node
that can pause the whole run: if triage found anything that needs a
human's judgment, it calls LangGraph's native interrupt() and the graph
stops there until someone resumes it with decisions.
"""

from __future__ import annotations

from langgraph.types import interrupt

from intercompany_close_agent.eliminations.engine import (
    build_elimination_from_exception,
    build_elimination_from_known_leg,
    build_eliminations,
)
from intercompany_close_agent.graph.state import CloseState
from intercompany_close_agent.matching.engine import match_transactions
from intercompany_close_agent.models.review import ReviewAction, ReviewDecision
from intercompany_close_agent.triage.models import TriageClassification
from intercompany_close_agent.triage.node import triage_all


def ingest(state: CloseState) -> dict:
    # entities / ic_transactions / trial_balance are loaded by the caller
    # (CLI or dashboard) before the graph runs -- this node is where a real
    # system would hit the source files or APIs directly. It's kept as an
    # explicit step so the pipeline's shape matches a real close: ingest is
    # its own stage, even though in this project the loading already
    # happened before invoke() was called.
    n_legs = len(state.get("ic_transactions", []))
    return {"audit_trail": state.get("audit_trail", []) + [f"ingested {n_legs} IC transaction legs"]}


def normalize(state: CloseState) -> dict:
    # COA mapping already happened in the loader (ingest/loaders.py). This
    # stage exists so the graph's shape says explicitly "we normalized
    # before matching" -- a real system might do FX translation or entity
    # eliminations-scope filtering here.
    return {"audit_trail": state["audit_trail"] + ["normalized ledger data"]}


def match(state: CloseState) -> dict:
    result = match_transactions(state["ic_transactions"])
    return {
        "clean_pairs": result.clean_pairs,
        "exceptions": result.exceptions,
        "audit_trail": state["audit_trail"]
        + [f"matched {len(result.clean_pairs)} clean pairs, {len(result.exceptions)} exceptions"],
    }


def triage(state: CloseState) -> dict:
    # Entity master data goes in so triage can weigh who booked the balance,
    # not just what the numbers say: a manually loaded entity's data carries
    # more risk than one that interfaces straight from the source ERP.
    entities_by_code = {entity.code: entity for entity in state.get("entities", [])}
    results = triage_all(state["exceptions"], entities_by_code)
    return {
        "triage_results": results,
        "audit_trail": state["audit_trail"] + [f"triaged {len(results)} exceptions"],
    }


def human_review(state: CloseState) -> dict:
    """Pause the run for anything triage flagged as needing a human's judgment.

    Everything else in this graph is deterministic or already covered by
    unit tests; this is the one place the pipeline is designed to stop and
    hand control back to a person. If nothing needs review, it's a no-op --
    interrupt() is never called, so the run flows straight through.
    """
    exceptions_by_reference = {exc.reference: exc for exc in state["exceptions"]}
    triage_by_reference = {t.reference: t for t in state["triage_results"]}

    pending = [
        {
            "reference": ref,
            "exception_type": exc.exception_type.value,
            "materiality": exc.materiality.value,
            "net_amount": str(exc.net_amount),
            "detected_reason": exc.detected_reason,
            "rationale": triage_by_reference[ref].rationale,
            "confidence": triage_by_reference[ref].confidence,
        }
        for ref, exc in exceptions_by_reference.items()
        if triage_by_reference[ref].classification == TriageClassification.NEEDS_HUMAN_JUDGMENT
    ]

    if not pending:
        return {"audit_trail": state["audit_trail"] + ["no exceptions needed human review"]}

    # Pauses the entire graph run here. On resume, this line returns
    # whatever value the caller passed to Command(resume=...) -- expected
    # to be a list of decision dicts, one per pending reference.
    decisions_payload = interrupt({"pending_review": pending})

    decisions = [ReviewDecision.model_validate(d) for d in decisions_payload]
    return {
        "review_decisions": decisions,
        "audit_trail": state["audit_trail"] + [f"received {len(decisions)} human review decisions"],
    }


def finalize(state: CloseState) -> dict:
    """Build the final elimination set: clean pairs, auto-resolved exceptions,
    and anything a human approved -- in that order, skipping whatever was
    rejected or is still pending.
    """
    eliminations = build_eliminations(state["clean_pairs"])
    notes: list[str] = []

    triage_by_reference = {t.reference: t for t in state["triage_results"]}
    exceptions_by_reference = {exc.reference: exc for exc in state["exceptions"]}
    decisions_by_reference = {d.reference: d for d in state.get("review_decisions", [])}

    for ref, exc in exceptions_by_reference.items():
        triage_result = triage_by_reference[ref]

        if triage_result.classification == TriageClassification.AUTO_RESOLVABLE:
            eliminations.append(build_elimination_from_exception(exc, note="auto-resolved by triage"))
            continue

        decision = decisions_by_reference.get(ref)
        if decision is None or decision.action == ReviewAction.REJECT:
            continue  # still pending, or the reviewer decided not to book it

        note = f"human-approved ({decision.action.value})"
        if decision.reviewer_note:
            note = f"{note}: {decision.reviewer_note}"

        if len(exc.legs) == 2:
            eliminations.append(
                build_elimination_from_exception(exc, note=note, override_amount=decision.override_amount)
            )
        elif len(exc.legs) == 1 and decision.override_amount is not None:
            # MISSING_COUNTERPARTY: there's no second system leg to derive an
            # amount from, so an approval only produces an elimination when
            # the reviewer supplied the amount to book.
            eliminations.append(
                build_elimination_from_known_leg(exc.legs[0], decision.override_amount, note=note)
            )
        else:
            # DUPLICATE_REFERENCE (or a MISSING_COUNTERPARTY approved with no
            # amount supplied) -- out of scope for this project's automated
            # booking; the audit trail records that it needs offline follow-up.
            notes.append(f"{ref}: approved but not booked automatically -- needs an amount or manual resolution")

    return {
        "eliminations": eliminations,
        "audit_trail": state["audit_trail"] + notes + [f"finalized {len(eliminations)} eliminations"],
    }
