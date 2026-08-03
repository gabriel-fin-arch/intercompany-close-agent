"""Elimination journal entries generated from matched intercompany pairs.

A consolidation elimination removes the intercompany balance from the
group's books: whatever one entity recorded as a receivable or payable
against another entity within the group nets out and disappears at the
group level. This only ever runs on pairs the matching engine already
cleared -- anything still uncertain belongs in an ICException, not here.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class JournalLineType(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class JournalLine(BaseModel):
    entity_code: str
    account_code: str
    line_type: JournalLineType
    amount: Decimal = Field(description="Always positive; the debit/credit side is carried by line_type.")


class Elimination(BaseModel):
    """A balanced elimination JE for one matched intercompany pair."""

    reference: str
    lines: list[JournalLine]
    narrative: str = Field(default="", description="Short explanation of what's being eliminated and why.")

    @model_validator(mode="after")
    def _check_balances(self) -> Elimination:
        debits = sum((line.amount for line in self.lines if line.line_type == JournalLineType.DEBIT), Decimal("0"))
        credits = sum((line.amount for line in self.lines if line.line_type == JournalLineType.CREDIT), Decimal("0"))
        if debits != credits:
            raise ValueError(f"elimination {self.reference} does not balance: debits={debits} credits={credits}")
        return self
