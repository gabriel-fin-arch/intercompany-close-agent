"""Control-account reconciliation results.

Before eliminating anything, a close should confirm that the intercompany
subledger it's about to work from actually agrees with the intercompany
control accounts on each entity's trial balance. If they disagree, every
elimination downstream is built on a number the general ledger doesn't
recognise -- which is a different, and usually worse, problem than any
individual balance failing to match its counterparty.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class TrialBalanceVariance(BaseModel):
    """One entity's intercompany position, subledger vs. trial balance."""

    entity_code: str
    ledger_total: Decimal = Field(
        description="Net intercompany position for this entity per the IC subledger."
    )
    trial_balance_total: Decimal = Field(
        description="Net of the entity's IC receivable and IC payable control accounts."
    )
    variance: Decimal = Field(description="ledger_total - trial_balance_total.")
    within_tolerance: bool

    def __str__(self) -> str:  # pragma: no cover - display helper
        return (
            f"{self.entity_code}: subledger {self.ledger_total} vs TB {self.trial_balance_total} "
            f"(variance {self.variance})"
        )
