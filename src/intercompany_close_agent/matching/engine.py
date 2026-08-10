"""Deterministic intercompany matching engine.

Groups each entity's IC transaction leg by reference and pairs it against
its counterparty's mirror leg. No LLM calls, no I/O -- this is the part of
the system that has to be exactly right, which is also why it's the part
with full unit test coverage.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction

# Matching tolerance. Two components, because a flat absolute number treats a
# USD 500 balance and a USD 250,000 one as if they carried the same risk:
#
#   floor  -- sub-unit differences are arithmetic noise at any size. USD 1.00.
#   rate   -- 0.01% of the larger leg, so tolerance scales with the balance.
#
# The effective tolerance is whichever is larger. Sized so genuine FX drift
# still fails: converting the same balance at two rates typically moves it by
# tenths of a percent upward, an order of magnitude past 0.01%.
AMOUNT_TOLERANCE_FLOOR = Decimal("1.00")
AMOUNT_TOLERANCE_RATE = Decimal("0.0001")

# Above this residual an exception is banded HIGH, below it LOW. This is an
# *operational* threshold, not a statutory one, and deliberately much tighter
# than audit materiality would be for a group this size: an intercompany break
# is a signal that a process failed somewhere, and a controller wants to see
# that well before it becomes a misstatement risk. The banding is only an
# input to triage -- it decides nothing on its own.
MATERIALITY_THRESHOLD = Decimal("5000.00")


def amount_tolerance_for(amount: Decimal) -> Decimal:
    """Tolerance applicable to a balance of this size."""
    return max(AMOUNT_TOLERANCE_FLOOR, abs(amount) * AMOUNT_TOLERANCE_RATE)


class MatchResult:
    """Everything the matching pass produced for one run."""

    def __init__(self, clean_pairs: list[tuple[ICTransaction, ICTransaction]], exceptions: list[ICException]) -> None:
        self.clean_pairs = clean_pairs
        self.exceptions = exceptions

    def summary(self) -> dict[str, int]:
        """Counts by exception type, plus the clean-pair count, for reporting."""
        counts: dict[str, int] = {"clean_pairs": len(self.clean_pairs)}
        for exc in self.exceptions:
            key = exc.exception_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts


def _materiality_for(amount: Decimal) -> Materiality:
    return Materiality.HIGH if abs(amount) >= MATERIALITY_THRESHOLD else Materiality.LOW


def _counterparties_consistent(a: ICTransaction, b: ICTransaction) -> bool:
    return a.entity_code == b.counterparty_code and b.entity_code == a.counterparty_code


def _accounting_period(leg: ICTransaction) -> tuple[int, int]:
    """The (year, month) this leg lands in.

    Elapsed days between two bookings is the wrong question. Two legs eight
    days apart inside the same month both make it into the same close and
    consolidate fine; two legs one day apart across a month end do not. What
    matters is which period each side falls into, not the gap between them.
    Assumes calendar monthly periods, which is what this group reports on.
    """
    return leg.transaction_date.year, leg.transaction_date.month


def _period_label(leg: ICTransaction) -> str:
    return leg.transaction_date.strftime("%Y-%m")


def match_transactions(transactions: list[ICTransaction]) -> MatchResult:
    """Pair up IC transaction legs by reference and flag whatever's left over.

    Handles the simplest case first: a reference with exactly one leg means
    the counterparty never booked its side at all. Everything else -- amount
    checks, counterparty consistency, timing -- gets layered on next.
    """
    by_reference: dict[str, list[ICTransaction]] = defaultdict(list)
    for txn in transactions:
        by_reference[txn.reference].append(txn)

    clean_pairs: list[tuple[ICTransaction, ICTransaction]] = []
    exceptions: list[ICException] = []

    for reference, legs in by_reference.items():
        self_dealt = [leg for leg in legs if leg.entity_code == leg.counterparty_code]
        if self_dealt:
            # An entity cannot hold an intercompany balance with itself. Netting
            # this would produce an entry that debits and credits the same
            # entity -- balanced, meaningless, and hiding a mapping error in
            # the source data.
            net = sum((leg.amount for leg in legs), Decimal("0"))
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.SELF_DEALING,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(max(abs(leg.amount) for leg in legs)),
                    detected_reason=(
                        f"{reference}: {self_dealt[0].entity_code} is booked as its own "
                        f"counterparty, which points at a mapping error rather than a real "
                        f"intercompany balance."
                    ),
                )
            )
            continue

        if len(legs) == 1:
            leg = legs[0]
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.MISSING_COUNTERPARTY,
                    legs=legs,
                    net_amount=leg.amount,
                    materiality=_materiality_for(leg.amount),
                    detected_reason=(
                        f"{leg.entity_code} booked {reference} against {leg.counterparty_code}, "
                        f"but no mirror leg was found under this reference."
                    ),
                )
            )
            continue

        if len(legs) > 2:
            net = sum((leg.amount for leg in legs), Decimal("0"))
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.DUPLICATE_REFERENCE,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(net),
                    detected_reason=f"{len(legs)} legs share reference {reference}; expected exactly 2.",
                )
            )
            continue

        leg_a, leg_b = legs[0], legs[1]

        if not _counterparties_consistent(leg_a, leg_b):
            net = leg_a.amount + leg_b.amount
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.COUNTERPARTY_MISMATCH,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(max(abs(leg_a.amount), abs(leg_b.amount))),
                    detected_reason=(
                        f"{leg_a.entity_code} booked {reference} against {leg_a.counterparty_code}, but "
                        f"{leg_b.entity_code} booked it against {leg_b.counterparty_code} instead of "
                        f"{leg_a.entity_code}."
                    ),
                )
            )
            continue

        if leg_a.currency != leg_b.currency:
            # Netting these would mean applying an implicit 1:1 rate between two
            # different currencies. FX translation is out of scope for this
            # project, so there is no rate to apply and no honest way to net
            # them -- it goes to a human, whatever the amounts look like.
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.CURRENCY_MISMATCH,
                    legs=legs,
                    net_amount=Decimal("0"),
                    materiality=_materiality_for(max(abs(leg_a.amount), abs(leg_b.amount))),
                    detected_reason=(
                        f"{reference}: {leg_a.entity_code} booked {leg_a.currency} and "
                        f"{leg_b.entity_code} booked {leg_b.currency}; the two legs cannot be "
                        f"netted without an FX rate."
                    ),
                )
            )
            continue

        if leg_a.amount != 0 and leg_b.amount != 0 and (leg_a.amount > 0) == (leg_b.amount > 0):
            # A clean pair always has one receivable and one payable leg. When
            # both point the same way, at least one entity has the balance
            # backwards -- and nothing in the ledger says which. This is a
            # different problem from an amount that's merely off: netting two
            # same-direction legs would produce an elimination in an
            # arbitrary, possibly wrong, direction rather than a residual.
            side = "receivable" if leg_a.amount > 0 else "payable"
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.SIGN_MISMATCH,
                    legs=legs,
                    net_amount=leg_a.amount + leg_b.amount,
                    materiality=_materiality_for(max(abs(leg_a.amount), abs(leg_b.amount))),
                    detected_reason=(
                        f"{reference}: {leg_a.entity_code} and {leg_b.entity_code} both booked "
                        f"this as a {side}; a real balance has one of each, and the ledger "
                        f"doesn't say which side has the sign backwards."
                    ),
                )
            )
            continue

        net = leg_a.amount + leg_b.amount
        tolerance = amount_tolerance_for(max(abs(leg_a.amount), abs(leg_b.amount)))
        if abs(net) > tolerance:
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.AMOUNT_MISMATCH,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(net),
                    detected_reason=(
                        f"{reference}: legs net to {net} instead of zero "
                        f"(tolerance for a balance this size is {tolerance})."
                    ),
                )
            )
            continue

        if _accounting_period(leg_a) != _accounting_period(leg_b):
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.TIMING_GAP,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(max(abs(leg_a.amount), abs(leg_b.amount))),
                    detected_reason=(
                        f"{reference}: {leg_a.entity_code} booked in "
                        f"{_period_label(leg_a)} but {leg_b.entity_code} booked in "
                        f"{_period_label(leg_b)}; the balance straddles the close cutoff."
                    ),
                )
            )
            continue

        clean_pairs.append((leg_a, leg_b))

    return MatchResult(clean_pairs=clean_pairs, exceptions=exceptions)
