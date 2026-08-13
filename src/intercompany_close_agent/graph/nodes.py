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
    elimination_residuals,
)
from intercompany_close_agent.graph.state import CloseState
from intercompany_close_agent.matching.engine import match_transactions
from intercompany_close_agent.models.elimination import Elimination
from intercompany_close_agent.models.exception import ExceptionType, ICException
from intercompany_close_agent.models.review import ReviewAction, ReviewDecision
from intercompany_close_agent.reconciliation.tieout import out_of_tolerance, reconcile_to_trial_balance
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


def reconcile(state: CloseState) -> dict:
    """Tie the IC subledger to the trial balance control accounts.

    Deliberately does not stop the run. A control-account variance is an
    entity-level data problem for someone to chase, not a per-balance
    judgment call, so it's reported and carried forward rather than routed
    into the human_review interrupt -- the reviewer worklist stays about
    individual balances, and this stays visible in the audit trail.
    """
    variances = reconcile_to_trial_balance(state["ic_transactions"], state["trial_balance"])
    breaks = out_of_tolerance(variances)

    trail = state["audit_trail"]
    if breaks:
        trail = trail + [
            f"control account tie-out: {len(breaks)} of {len(variances)} entities do not tie"
        ]
        trail = trail + [
            f"  {v.entity_code}: subledger {v.ledger_total} vs TB {v.trial_balance_total}"
            f" (variance {v.variance})"
            for v in breaks
        ]
    else:
        trail = trail + [f"control account tie-out: all {len(variances)} entities tie"]

    return {"tb_variances": variances, "audit_trail": trail}


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
            # None for CURRENCY_MISMATCH -- kept as None here rather than
            # stringified, so the CLI and dashboard can each render "not
            # applicable" instead of a literal "None" or "0" that a reviewer
            # editing the amount could end up submitting as-is.
            "net_amount": str(exc.net_amount) if exc.net_amount is not None else None,
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


def _residual_notes(ref: str, exc: ICException, elim: Elimination) -> list[str]:
    """Audit-trail lines for any control-account residual this elimination leaves standing.

    An elimination built from an exception (see
    eliminations/engine.py::build_elimination_from_exception) can clear the
    receivable side exactly and still leave the payable side short, or over,
    of what that entity actually booked. That's worth a line in the audit
    trail rather than a number that quietly stops tying out after the close
    is done -- the same reasoning `reconcile` (above) already applies before
    matching starts.
    """
    return [
        f"{ref}: eliminated at {elim.lines[0].amount}, but {entity_code}'s control account "
        f"carries an unexplained residual of {residual} after posting"
        for entity_code, residual in elimination_residuals(exc, elim)
    ]


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
            elim = build_elimination_from_exception(exc, note="auto-resolved by triage")
            eliminations.append(elim)
            notes.extend(_residual_notes(ref, exc, elim))
            continue

        decision = decisions_by_reference.get(ref)
        if decision is None or decision.action == ReviewAction.REJECT:
            continue  # still pending, or the reviewer decided not to book it

        if decision.override_amount is not None and decision.override_amount <= 0:
            # The reviewer's amount is the one human-supplied number that
            # reaches a journal entry, and it's free text from the dashboard.
            # A negative would post a direction-inverted "balanced" entry
            # (a -500 debit is really a 500 credit); a zero would book an
            # elimination that clears nothing. JournalLine forbids both at
            # the model level -- caught here first so a fat-fingered amount
            # degrades to an unbooked worklist item with a reason, instead
            # of crashing the resume the reviewer depends on.
            notes.append(
                f"{ref}: approved with an override amount of {decision.override_amount}, but an "
                f"elimination amount must be a positive number; not booked, needs a corrected amount"
            )
            continue

        note = f"human-approved ({decision.action.value})"
        if decision.reviewer_note:
            note = f"{note}: {decision.reviewer_note}"

        if exc.exception_type == ExceptionType.SIGN_MISMATCH:
            # Both legs are booked on the same side, so there's no
            # unambiguous receivable/payable pair to derive an entry from --
            # approving this isn't enough, unlike an amount mismatch or a
            # timing gap. build_elimination_from_exception would have to
            # guess which entity has the sign backwards, and it refuses to.
            notes.append(
                f"{ref}: approved but not booked automatically -- both legs share a sign, "
                f"so which side has it backwards isn't knowable from the ledger; needs manual "
                f"resolution"
            )
        elif exc.exception_type == ExceptionType.CURRENCY_MISMATCH and decision.override_amount is None:
            # Approving alone books at one leg's own amount -- fine for an
            # AMOUNT_MISMATCH, where both legs are in the same currency, but
            # here that would apply exactly the implicit 1:1 rate this
            # exception type exists to refuse. Only a reviewer-supplied
            # amount (via edit), already converted to the reporting
            # currency, is safe to book.
            notes.append(
                f"{ref}: approved but not booked automatically -- legs are in different "
                f"currencies with no FX rate to net them; needs a reviewer-supplied amount "
                f"or manual resolution"
            )
        elif len(exc.legs) == 2:
            elim = build_elimination_from_exception(exc, note=note, override_amount=decision.override_amount)
            eliminations.append(elim)
            notes.extend(_residual_notes(ref, exc, elim))
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
