"""Deterministic elimination journal entry generation.

Takes the clean pairs the matching engine already cleared and turns each one
into a balanced elimination JE. The receivable side is credited off and the
payable side is debited off, both on the group's intercompany elimination
account -- which GL account that maps to at the entity level doesn't matter
for this project's scope, it's always the same standard elimination line.
"""

from __future__ import annotations

from decimal import Decimal

from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.models.ledger import ICTransaction

ELIMINATION_ACCOUNT = "9999-IC-ELIM"


def _receivable_and_payable(leg_a: ICTransaction, leg_b: ICTransaction) -> tuple[ICTransaction, ICTransaction]:
    """Sort two legs of the same balance into (receivable leg, payable leg)."""
    return (leg_a, leg_b) if leg_a.amount > 0 else (leg_b, leg_a)


def _elimination_lines(payable_leg: ICTransaction, receivable_leg: ICTransaction, amount: Decimal) -> list[JournalLine]:
    return [
        JournalLine(
            entity_code=payable_leg.entity_code,
            account_code=ELIMINATION_ACCOUNT,
            line_type=JournalLineType.DEBIT,
            amount=amount,
        ),
        JournalLine(
            entity_code=receivable_leg.entity_code,
            account_code=ELIMINATION_ACCOUNT,
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
    lines = _elimination_lines(payable_leg, receivable_leg, amount)

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
    lines = _elimination_lines(payable_leg, receivable_leg, amount)

    narrative = (
        f"Eliminate intercompany balance {exc.reference} ({exc.exception_type.value}): "
        f"{payable_leg.entity_code} owed {receivable_leg.entity_code} {amount} {receivable_leg.currency}."
    )
    if note:
        narrative = f"{narrative} [{note}]"

    return Elimination(reference=exc.reference, lines=lines, narrative=narrative)


def build_elimination_from_known_leg(known_leg: ICTransaction, amount: Decimal, note: str = "") -> Elimination:
    """Build an elimination JE for a MISSING_COUNTERPARTY or DUPLICATE_REFERENCE
    exception a human has approved.

    There's no second system-of-record leg to derive an amount from here --
    that's the whole reason these exception types always need a human. The
    reviewer supplies the amount (via ReviewDecision.override_amount); this
    just books it against the counterparty the known leg already names.
    """
    receivable_leg, payable_leg = (
        (known_leg, None) if known_leg.amount > 0 else (None, known_leg)
    )
    if receivable_leg is not None:
        payable_entity = known_leg.counterparty_code
        receivable_entity = known_leg.entity_code
    else:
        payable_entity = known_leg.entity_code
        receivable_entity = known_leg.counterparty_code

    lines = [
        JournalLine(entity_code=payable_entity, account_code=ELIMINATION_ACCOUNT, line_type=JournalLineType.DEBIT, amount=amount),
        JournalLine(entity_code=receivable_entity, account_code=ELIMINATION_ACCOUNT, line_type=JournalLineType.CREDIT, amount=amount),
    ]

    narrative = (
        f"Eliminate intercompany balance {known_leg.reference} (human-supplied amount, "
        f"no system counterparty leg): {payable_entity} owed {receivable_entity} {amount} {known_leg.currency}."
    )
    if note:
        narrative = f"{narrative} [{note}]"

    return Elimination(reference=known_leg.reference, lines=lines, narrative=narrative)
