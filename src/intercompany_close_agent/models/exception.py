"""Matching exceptions -- what's left over once the clean IC pairs are pulled out.

Deliberately free of anything an LLM would produce (no confidence score, no
narrative). Those live on TriageResult, built later in the graph layer, so
an ICException means the same thing whether triage ran against a live model
or the offline rule-based fallback -- the deterministic matcher never knows
or cares which one is coming.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from intercompany_close_agent.models.ledger import ICTransaction


class ExceptionType(str, Enum):
    MISSING_COUNTERPARTY = "missing_counterparty"
    COUNTERPARTY_MISMATCH = "counterparty_mismatch"
    AMOUNT_MISMATCH = "amount_mismatch"
    TIMING_GAP = "timing_gap"
    DUPLICATE_REFERENCE = "duplicate_reference"


class Materiality(str, Enum):
    """Coarse magnitude banding, decided purely by a dollar threshold.

    Not the same thing as "auto-resolvable vs needs judgment" -- materiality
    only measures size. A tiny counterparty mismatch is still a counterparty
    mismatch and still needs a human to say who's right; it just isn't going
    to move the group's numbers much either way.
    """

    LOW = "low"
    HIGH = "high"


class ICException(BaseModel):
    """One intercompany reference where the legs didn't resolve cleanly."""

    reference: str
    exception_type: ExceptionType
    legs: list[ICTransaction] = Field(description="Every transaction leg found under this reference.")
    net_amount: Decimal = Field(description="Sum of the legs' amounts -- the residual that isn't explained.")
    materiality: Materiality
    detected_reason: str = Field(description="Plain-language, code-generated explanation of what the matcher found.")

    @property
    def involved_entity_codes(self) -> set[str]:
        """Every entity named by this exception, on either side of the balance.

        Includes counterparty codes, not just the entities that actually
        booked a leg -- for a missing counterparty booking, the entity that
        didn't book anything is precisely the one worth knowing about.
        """
        codes: set[str] = set()
        for leg in self.legs:
            codes.add(leg.entity_code)
            codes.add(leg.counterparty_code)
        return codes
