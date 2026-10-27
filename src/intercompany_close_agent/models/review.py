"""A human reviewer's decision on one exception raised to them.

Every decision is logged, whichever way it goes -- approve, reject, or edit
the proposed amount -- so the close has an audit trail of who decided what,
not just what ended up booked.

Names are typed in, not authenticated. They make the run's record say who
prepared it and who decided each item, and let finalize refuse a decision by
the preparer; they don't stop anyone typing someone else's name. That needs
the group's own sign-in, which this project doesn't have.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def same_person(a: str, b: str) -> bool:
    """Whether two typed names are the same person, as far as text can tell.

    Case and spacing don't count, so "Ana Ruiz" and "ana  ruiz" are one
    person. Anything more (initials, nicknames) is beyond what a name typed
    into a form can show.
    """
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


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
    # Decimal reads "NaN" and "Infinity" as numbers. NaN can't even be compared
    # with zero, and an infinite amount fails ReviewDecision inside the resume,
    # the crash this function exists to prevent.
    if not amount.is_finite():
        raise ValueError(f"amount must be a number, e.g. 1234.56 (got {raw!r})")
    if amount <= 0:
        raise ValueError(f"amount must be a positive number (got {amount})")
    # The journal books cents. A third decimal would be rounded away on export,
    # so the entry in the run and the line in the file would disagree.
    cents = amount.quantize(Decimal("0.01"))
    if cents != amount:
        raise ValueError(f"amount can't have more than two decimal places (got {raw.strip()!r})")
    return cents


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class ReviewDecision(BaseModel):
    reference: str
    action: ReviewAction
    reviewer: PersonName = Field(description="Who made the decision. Must not be who prepared the run.")
    reviewer_note: str = ""
    override_amount: Decimal | None = Field(
        default=None,
        description="Only meaningful for action=edit -- the amount to eliminate instead of the raw residual.",
    )
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
