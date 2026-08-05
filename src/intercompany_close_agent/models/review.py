"""A human reviewer's decision on one exception raised to them.

Every decision is logged, whichever way it goes -- approve, reject, or edit
the proposed amount -- so the close has an audit trail of who decided what,
not just what ended up booked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class ReviewDecision(BaseModel):
    reference: str
    action: ReviewAction
    reviewer_note: str = ""
    override_amount: Decimal | None = Field(
        default=None,
        description="Only meaningful for action=edit -- the amount to eliminate instead of the raw residual.",
    )
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
