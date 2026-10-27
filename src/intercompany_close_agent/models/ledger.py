"""Trial balance and intercompany ledger line items.

These are the two feeds a close needs before it can run any eliminations:
the entity-level trial balance (context and account mapping) and the
intercompany ledger, where each entity records what it believes it owes to,
or is owed by, its counterparties within the group.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class TrialBalanceLine(BaseModel):
    """A single GL account balance for one entity at close."""

    entity_code: str
    account_code: str = Field(description="Group standard chart-of-accounts code, after COA mapping.")
    account_name: str
    balance: Decimal = Field(
        description=(
            "Balance in the group reporting currency (USD), like the IC ledger amounts: the tie-out "
            "compares the two directly, and nothing here translates from local currency. Debit "
            "positive, credit negative."
        )
    )


class ICTransaction(BaseModel):
    """One side of an intercompany balance, as booked by a single entity.

    A real intercompany balance always has two legs -- what entity A says it
    owes to, or is owed by, entity B, and entity B's mirror entry. Both legs
    show up as separate ICTransaction records; pairing them up (or flagging
    why they don't pair) is the whole point of the matching engine.
    """

    entity_code: str = Field(description="The entity that booked this leg.")
    counterparty_code: str = Field(description="The entity on the other side of the balance, as booked.")
    reference: str = Field(description="Intercompany reference used to pair the two legs of a balance.")
    amount: Decimal = Field(
        description=(
            "Signed amount in the reporting currency (USD). Positive means the entity "
            "records a receivable from the counterparty; negative means a payable."
        )
    )
    currency: str = Field(default="USD", description="Currency the amount is expressed in.")
    transaction_date: date = Field(description="Booking date of this leg.")
    description: str = Field(default="", description="Free-text memo as booked by the entity.")
