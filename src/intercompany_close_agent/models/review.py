"""A human reviewer's decision on one exception raised to them.

Every decision is logged, whichever way it goes -- approve, reject, or edit
the proposed amount -- so the close has an audit trail of who decided what,
not just what ended up booked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field


def parse_override_amount(raw: str | None) -> Decimal | None:
    """Parse a reviewer's free-text override amount from the dashboard.

    A blank field means "no override" -- an approve or reject, or an edit
    left empty. Anything else has to be a positive decimal: this number
    reaches a journal entry, where an unparseable string crashes the resume
    and a non-positive value books a direction-inverted or empty entry (the
    reason JournalLine.amount is constrained > 0). Raising a plain ValueError
    here lets the dashboard show the reviewer what's wrong instead of a
    stack trace, and finalize still re-checks the sign as a backstop.
    """
    if raw is None or raw.strip() == "":
        return None
    try:
        amount = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ValueError(f"amount must be a number, e.g. 1234.56 (got {raw!r})") from exc
    if amount <= 0:
        raise ValueError(f"amount must be a positive number (got {amount})")
    return amount


class ReviewAction(StrEnum):
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
