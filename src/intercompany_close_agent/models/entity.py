"""Legal entity master data.

Every consolidation cycle starts here: before matching a single transaction,
the group needs to know which legal entities are in scope, what currency
they report in locally, and whether their trial balance arrives through a
system interface or gets loaded by hand. That last flag matters more than it
looks -- non-interfaced entities are where timing and mapping errors tend to
show up at close.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """A single legal entity within the consolidated group."""

    code: str = Field(description="Short entity code used across the TB and IC ledger, e.g. 'US01'.")
    name: str = Field(description="Legal entity name.")
    region: str = Field(description="Reporting region, e.g. 'EMEA', 'US', 'LATAM', 'AFRICA'.")
    local_currency: str = Field(description="ISO 4217 code of the entity's local currency.")
    reporting_currency: str = Field(
        default="USD",
        description="Group reporting currency. Fixed at USD for this project's scope.",
    )
    interfaced: bool = Field(
        default=True,
        description=(
            "Whether the entity's trial balance loads automatically from the source ERP. "
            "Non-interfaced entities are loaded manually, which is exactly why they carry "
            "more risk of timing and mapping errors. Triage reads this: an exception "
            "involving a manually loaded entity is never auto-eliminated on the strength of "
            "being small, so one that would otherwise have been auto-resolved goes to a "
            "reviewer instead (see triage/rules.py)."
        ),
    )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code} ({self.name})"
