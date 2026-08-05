"""Deterministic elimination journal entry generation.

Takes the clean pairs the matching engine already cleared and turns each one
into a balanced elimination JE.

The entry clears the same control accounts the tie-out reads: the entity
that owes gets its intercompany payable debited, and the entity that's owed
gets its intercompany receivable credited. Booking both sides to a generic
"eliminations" account would balance just as well, but it would leave the
IC control accounts standing at group level -- which is precisely what an
elimination is supposed to remove, and precisely what reconciliation/ checks.
"""

from __future__ import annotations

from decimal import Decimal

from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.reconciliation.tieout import IC_PAYABLE_ACCOUNT, IC_RECEIVABLE_ACCOUNT


def _receivable_and_payable(leg_a: ICTransaction, leg_b: ICTransaction) -> tuple[ICTransaction, ICTransaction]:
    """Sort two legs of the same balance into (receivable leg, payable leg)."""
    return (leg_a, leg_b) if leg_a.amount > 0 else (leg_b, leg_a)


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
    return [build_elimination(pair) for pair in pairs]


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

    return Elimination(reference=exc.reference, lines=lines, narrative=narrative)


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
