"""Deterministic elimination journal entry generation.

Takes the clean pairs the matching engine already cleared and turns each one
into a balanced elimination JE. The receivable side is credited off and the
payable side is debited off, both on the group's intercompany elimination
account -- which GL account that maps to at the entity level doesn't matter
for this project's scope, it's always the same standard elimination line.
"""

from __future__ import annotations

from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.ledger import ICTransaction

ELIMINATION_ACCOUNT = "9999-IC-ELIM"


def build_elimination(pair: tuple[ICTransaction, ICTransaction]) -> Elimination:
    """Build a balanced elimination JE from one matched IC pair.

    One leg is positive (a receivable, as booked) and the other negative (a
    payable) -- that's what "matched" means coming out of the matching
    engine. Eliminating the balance means debiting whichever entity holds
    the payable and crediting whichever entity holds the receivable, for
    the same absolute amount, on the group elimination account.
    """
    leg_a, leg_b = pair
    receivable_leg, payable_leg = (leg_a, leg_b) if leg_a.amount > 0 else (leg_b, leg_a)
    amount = abs(receivable_leg.amount)

    lines = [
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

    narrative = (
        f"Eliminate intercompany balance {receivable_leg.reference}: "
        f"{payable_leg.entity_code} owed {receivable_leg.entity_code} {amount} {receivable_leg.currency}."
    )

    return Elimination(reference=receivable_leg.reference, lines=lines, narrative=narrative)


def build_eliminations(pairs: list[tuple[ICTransaction, ICTransaction]]) -> list[Elimination]:
    return [build_elimination(pair) for pair in pairs]
