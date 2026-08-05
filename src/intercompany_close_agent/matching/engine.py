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

# How close two legs' amounts need to be, in USD, to count as the same
# balance. Anything inside this is a rounding difference, not a real break.
# REVIEW: 5 cents is a reasonable starting point for a synthetic dataset; a
# real close would likely tie this to the group's own rounding policy.
AMOUNT_TOLERANCE = Decimal("0.05")

# Below this absolute USD residual, an exception is flagged LOW materiality.
# Above it, HIGH. This drives nothing on its own -- it's raw input for the
# triage step's later auto-resolvable / needs-judgment call.
# REVIEW: a real group would size this off its own SOX materiality
# threshold, not a flat number.
MATERIALITY_THRESHOLD = Decimal("1000.00")

# Legs booked more than this many days apart get flagged for a timing gap,
# even when the amounts line up perfectly -- a balance booked after the
# other entity's cutoff is still worth a look, not just a rounding note.
TIMING_TOLERANCE_DAYS = 2


class MatchResult:
    """Everything the matching pass produced for one run."""

    def __init__(self, clean_pairs: list[tuple[ICTransaction, ICTransaction]], exceptions: list[ICException]) -> None:
        self.clean_pairs = clean_pairs
        self.exceptions = exceptions


def _materiality_for(amount: Decimal) -> Materiality:
    return Materiality.HIGH if abs(amount) >= MATERIALITY_THRESHOLD else Materiality.LOW


def _counterparties_consistent(a: ICTransaction, b: ICTransaction) -> bool:
    return a.entity_code == b.counterparty_code and b.entity_code == a.counterparty_code


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

        net = leg_a.amount + leg_b.amount
        if abs(net) > AMOUNT_TOLERANCE:
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.AMOUNT_MISMATCH,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(net),
                    detected_reason=(
                        f"{reference}: legs net to {net} instead of zero (tolerance is {AMOUNT_TOLERANCE})."
                    ),
                )
            )
            continue

        day_gap = abs((leg_a.transaction_date - leg_b.transaction_date).days)
        if day_gap > TIMING_TOLERANCE_DAYS:
            exceptions.append(
                ICException(
                    reference=reference,
                    exception_type=ExceptionType.TIMING_GAP,
                    legs=legs,
                    net_amount=net,
                    materiality=_materiality_for(max(abs(leg_a.amount), abs(leg_b.amount))),
                    detected_reason=(
                        f"{reference}: legs are {day_gap} days apart ({leg_a.transaction_date} vs "
                        f"{leg_b.transaction_date}), beyond the {TIMING_TOLERANCE_DAYS}-day cutoff tolerance."
                    ),
                )
            )
            continue

        clean_pairs.append((leg_a, leg_b))

    return MatchResult(clean_pairs=clean_pairs, exceptions=exceptions)
