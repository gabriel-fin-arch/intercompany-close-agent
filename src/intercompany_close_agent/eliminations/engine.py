"""Deterministic elimination journal entry generation.

Takes the clean pairs the matching engine already cleared, or an exception a
human or triage cleared to book, and turns each one into a balanced
elimination JE.

The entry clears the same control accounts the tie-out reads: the entity
that owes gets its intercompany payable debited, and the entity that's owed
gets its intercompany receivable credited. Booking both sides to a generic
"eliminations" account would balance just as well, but it would leave the
IC control accounts standing at group level -- which is precisely what an
elimination is supposed to remove, and precisely what reconciliation/ checks.

The entry books the receivable leg's own amount on both sides, so the
receivable side always clears exactly. The payable side clears exactly only
when the legs net to zero. A clean pair can be off by anything inside the
matching tolerance -- USD 1.00, or 0.01% of a large balance -- and an
exception by more, which is why it's an exception. Either way, see
`elimination_residuals()` for what's left on the other side, and
`graph/nodes.py::finalize`, which surfaces whatever it finds rather than
letting the gap disappear.
"""

from __future__ import annotations

from decimal import Decimal

from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.reconciliation.tieout import IC_PAYABLE_ACCOUNT, IC_RECEIVABLE_ACCOUNT


def _receivable_and_payable(leg_a: ICTransaction, leg_b: ICTransaction) -> tuple[ICTransaction, ICTransaction]:
    """Sort two legs of the same balance into (receivable leg, payable leg).

    Assumes exactly one leg is positive and the other negative -- true for
    every clean pair the matcher produces, and for every AMOUNT_MISMATCH /
    TIMING_GAP exception, since the matcher routes same-signed legs into a
    SIGN_MISMATCH exception before either check ever sees them (see
    matching/engine.py). If both legs point the same way here anyway,
    there's no honest way to guess which one has the sign backwards, so
    this raises rather than picking a direction that might be wrong.
    """
    if leg_a.amount != 0 and leg_b.amount != 0 and (leg_a.amount > 0) == (leg_b.amount > 0):
        raise ValueError(
            f"cannot tell receivable from payable for {leg_a.reference}: both legs are "
            f"{'positive' if leg_a.amount > 0 else 'negative'} ({leg_a.amount}, {leg_b.amount})"
        )
    # Sorted on whichever leg has a sign. A leg booked at zero says nothing
    # about direction, so a positive leg is the receivable and a negative one
    # the payable, wherever the zero sits; sorting on the first leg alone put
    # a negative leg on the receivable side when the zero came first.
    return (leg_a, leg_b) if leg_a.amount > 0 or leg_b.amount < 0 else (leg_b, leg_a)


def receivable_amount(legs: list[ICTransaction]) -> Decimal:
    """What an elimination of these two legs books by default: the receivable leg's own amount.

    Zero when the entity on the receivable side booked nothing, and then there
    is nothing to book at that amount -- callers leave the balance unbooked
    with a reason rather than post an entry for zero.
    """
    receivable_leg, _ = _receivable_and_payable(legs[0], legs[1])
    return abs(receivable_leg.amount)


def _elimination_lines(payable_entity: str, receivable_entity: str, amount: Decimal) -> list[JournalLine]:
    """Debit the payable off the entity that owes, credit the receivable off the entity that's owed."""
    return [
        JournalLine(
            entity_code=payable_entity,
            account_code=IC_PAYABLE_ACCOUNT,
            line_type=JournalLineType.DEBIT,
            amount=amount,
        ),
        JournalLine(
            entity_code=receivable_entity,
            account_code=IC_RECEIVABLE_ACCOUNT,
            line_type=JournalLineType.CREDIT,
            amount=amount,
        ),
    ]


def build_elimination(pair: tuple[ICTransaction, ICTransaction]) -> Elimination:
    """Build a balanced elimination JE from one matched IC pair.

    One leg is positive (a receivable, as booked) and the other negative (a
    payable) -- that's what "matched" means coming out of the matching
    engine. Eliminating the balance means debiting whichever entity holds
    the payable and crediting whichever entity holds the receivable, for
    the same absolute amount, on the group elimination account.
    """
    leg_a, leg_b = pair
    receivable_leg, payable_leg = _receivable_and_payable(leg_a, leg_b)
    amount = abs(receivable_leg.amount)
    lines = _elimination_lines(payable_leg.entity_code, receivable_leg.entity_code, amount)

    narrative = (
        f"Eliminate intercompany balance {receivable_leg.reference}: "
        f"{payable_leg.entity_code} owed {receivable_leg.entity_code} {amount} {receivable_leg.currency}."
    )

    return Elimination(reference=receivable_leg.reference, lines=lines, narrative=narrative)


def build_eliminations(pairs: list[tuple[ICTransaction, ICTransaction]]) -> list[Elimination]:
    """Build eliminations for every matched pair that has something to eliminate.

    A pair whose receivable side is zero has nothing to eliminate at that
    amount -- posting a zero-value entry would balance perfectly and say
    nothing, and `JournalLine` refuses it. If the payable side isn't zero
    too, what it leaves standing is reported by `graph/nodes.py::finalize`.
    """
    return [build_elimination(pair) for pair in pairs if receivable_amount(list(pair)) > 0]


def elimination_residuals(legs: list[ICTransaction], elimination: Elimination) -> list[tuple[str, Decimal]]:
    """Per-entity control-account residual an elimination leaves standing.

    Takes the legs rather than the exception so it works for a clean pair
    too, whose legs can differ by up to the matching tolerance.

    `build_elimination_from_exception` books a single amount against both
    entities' control accounts -- the receivable leg's own amount by
    default, or a reviewer's override. Neither is guaranteed to equal what
    a given entity actually booked: that's the whole reason the exception
    existed in the first place (an unexplained residual, an override that
    doesn't match either leg). When it doesn't match, that entity's control
    account won't net to zero after this entry posts, which is exactly what
    `reconciliation/tieout.py` checks for before matching starts. This is
    the same check run the other way: not "did the input data already tie,"
    but "did eliminating it just introduce a new break." Callers surface
    whatever this returns instead of letting the gap disappear silently.

    Sign follows what's left of the entity's original position: positive
    means under-cleared (the entity still carries part of its original
    balance), negative means over-cleared (posting flipped it to the
    opposite side of zero).
    """
    posted_by_entity = {line.entity_code: line.amount for line in elimination.lines}
    residuals: list[tuple[str, Decimal]] = []
    for leg in legs:
        posted = posted_by_entity.get(leg.entity_code)
        if posted is None:
            continue
        residual = abs(leg.amount) - posted
        if residual != 0:
            residuals.append((leg.entity_code, residual))
    return residuals


def build_elimination_from_exception(
    exc: ICException,
    note: str = "",
    override_amount: Decimal | None = None,
) -> Elimination:
    """Build an elimination JE from an exception's two legs.

    Only ever called for AMOUNT_MISMATCH / TIMING_GAP exceptions -- the ones
    where a genuine intercompany balance exists on both sides, it just
    didn't net exactly to zero or landed outside the timing tolerance.
    MISSING_COUNTERPARTY, DUPLICATE_REFERENCE and COUNTERPARTY_MISMATCH
    exceptions never reach this without an explicit human decision on what
    to book, since there's no unambiguous pair of legs to eliminate.
    SIGN_MISMATCH is routed around this function entirely in
    `graph/nodes.py::finalize` for the same reason: with both legs pointing
    the same way, there's no unambiguous receivable/payable pair to derive
    an entry from either, and `_receivable_and_payable` raises if it's
    called with one anyway.

    Books at the receivable leg's own amount by default -- not the
    residual, and not a value in between -- so at least the receivable side
    always clears exactly. That leaves the payable side carrying whatever
    didn't net, unless an override happens to match it. This function
    doesn't hide that: see `elimination_residuals`, which it calls before
    returning, and which the caller (`graph/nodes.py::finalize`) surfaces in
    the audit trail whenever it finds one.
    """
    if len(exc.legs) != 2:
        raise ValueError(f"cannot build an elimination from {len(exc.legs)} legs (reference {exc.reference})")

    leg_a, leg_b = exc.legs
    receivable_leg, payable_leg = _receivable_and_payable(leg_a, leg_b)
    amount = override_amount if override_amount is not None else abs(receivable_leg.amount)
    lines = _elimination_lines(payable_leg.entity_code, receivable_leg.entity_code, amount)

    narrative = (
        f"Eliminate intercompany balance {exc.reference} ({exc.exception_type.value}): "
        f"{payable_leg.entity_code} owed {receivable_leg.entity_code} {amount} {receivable_leg.currency}."
    )
    if note:
        narrative = f"{narrative} [{note}]"

    elimination = Elimination(reference=exc.reference, lines=lines, narrative=narrative)

    residuals = elimination_residuals(exc.legs, elimination)
    if residuals:
        residual_text = "; ".join(
            f"{entity_code} carries an unexplained residual of {residual} after posting"
            for entity_code, residual in residuals
        )
        elimination = elimination.model_copy(update={"narrative": f"{elimination.narrative} [{residual_text}]"})

    return elimination


def build_elimination_from_known_leg(known_leg: ICTransaction, amount: Decimal, note: str = "") -> Elimination:
    """Build an elimination JE for an approved MISSING_COUNTERPARTY exception.

    There's no second system-of-record leg to derive an amount from here --
    that's the whole reason this exception type always needs a human. The
    reviewer supplies the amount (via ReviewDecision.override_amount); this
    books it against the counterparty the known leg already names.

    A positive known leg is a receivable, so the entity that booked it gets
    the credit and the counterparty it named gets the debit. A negative one
    is a payable, so the two swap.
    """
    if known_leg.amount > 0:
        receivable_entity, payable_entity = known_leg.entity_code, known_leg.counterparty_code
    else:
        receivable_entity, payable_entity = known_leg.counterparty_code, known_leg.entity_code

    lines = _elimination_lines(payable_entity, receivable_entity, amount)

    narrative = (
        f"Eliminate intercompany balance {known_leg.reference} (human-supplied amount, "
        f"no system counterparty leg): {payable_entity} owed {receivable_entity} {amount} {known_leg.currency}."
    )
    if note:
        narrative = f"{narrative} [{note}]"

    return Elimination(reference=known_leg.reference, lines=lines, narrative=narrative)
