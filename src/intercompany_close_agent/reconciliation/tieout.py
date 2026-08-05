"""Tie the intercompany subledger back to the trial balance control accounts.

This runs before matching, and it answers a question matching can't: does
the intercompany data we're about to eliminate from actually agree with
what each entity's general ledger says its intercompany position is?

A per-balance mismatch is a reconciliation item. A control-account
variance is a data problem -- it means the subledger and the GL disagree
about the totals, so every elimination built off that subledger is
suspect. Worth knowing before you start, not after.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from intercompany_close_agent.matching.engine import AMOUNT_TOLERANCE_FLOOR
from intercompany_close_agent.models.control import TrialBalanceVariance
from intercompany_close_agent.models.ledger import ICTransaction, TrialBalanceLine

# Group-standard account codes, i.e. post-COA-mapping (see ingest/loaders.py).
IC_RECEIVABLE_ACCOUNT = "IC_RECEIVABLE"
IC_PAYABLE_ACCOUNT = "IC_PAYABLE"

# Derived from the matching tolerance rather than set independently: a group
# that treats a difference as rounding noise when matching one balance can't
# coherently call the same difference a control failure when totalling them.
# The floor is used, not the relative rate -- this compares totals, and a
# percentage of a total would scale the tolerance with the size of the
# entity's book rather than with the error.
TIEOUT_TOLERANCE = AMOUNT_TOLERANCE_FLOOR


def reconcile_to_trial_balance(
    transactions: list[ICTransaction],
    trial_balance: list[TrialBalanceLine],
) -> list[TrialBalanceVariance]:
    """Compare each entity's IC subledger position to its TB control accounts.

    Both sides use the same sign convention: positive is a receivable, and
    negative is a payable, so the two totals should net to the same number
    for every entity in scope.
    """
    ledger_by_entity: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for txn in transactions:
        ledger_by_entity[txn.entity_code] += txn.amount

    tb_by_entity: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for line in trial_balance:
        if line.account_code in (IC_RECEIVABLE_ACCOUNT, IC_PAYABLE_ACCOUNT):
            tb_by_entity[line.entity_code] += line.balance

    variances: list[TrialBalanceVariance] = []
    for entity_code in sorted(set(ledger_by_entity) | set(tb_by_entity)):
        ledger_total = ledger_by_entity[entity_code]
        tb_total = tb_by_entity[entity_code]
        variance = ledger_total - tb_total
        variances.append(
            TrialBalanceVariance(
                entity_code=entity_code,
                ledger_total=ledger_total,
                trial_balance_total=tb_total,
                variance=variance,
                within_tolerance=abs(variance) <= TIEOUT_TOLERANCE,
            )
        )

    return variances


def out_of_tolerance(variances: list[TrialBalanceVariance]) -> list[TrialBalanceVariance]:
    return [v for v in variances if not v.within_tolerance]
