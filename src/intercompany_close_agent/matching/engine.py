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

# Below this absolute USD residual, an exception is flagged LOW materiality.
# Above it, HIGH. This drives nothing on its own -- it's raw input for the
# triage step's later auto-resolvable / needs-judgment call.
# REVIEW: a real group would size this off its own SOX materiality
# threshold, not a flat number.
MATERIALITY_THRESHOLD = Decimal("1000.00")


class MatchResult:
    """Everything the matching pass produced for one run."""

    def __init__(self, clean_pairs: list[tuple[ICTransaction, ICTransaction]], exceptions: list[ICException]) -> None:
        self.clean_pairs = clean_pairs
        self.exceptions = exceptions


def _materiality_for(amount: Decimal) -> Materiality:
    return Materiality.HIGH if abs(amount) >= MATERIALITY_THRESHOLD else Materiality.LOW


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

        # Two legs, nothing checked yet -- treat as clean for now.
        leg_a, leg_b = legs[0], legs[1]
        clean_pairs.append((leg_a, leg_b))

    return MatchResult(clean_pairs=clean_pairs, exceptions=exceptions)
