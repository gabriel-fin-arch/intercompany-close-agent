"""The close policy: the numbers that decide what a person has to look at.

Materiality and the matching tolerance are judgment calls a group makes, not
facts about the code, so they're read from a policy file instead of being
edited into the source. Without one, the defaults below apply, and they're
the values the project has always used. The reasoning behind each default
stays with it; `docs/architecture.md` has the longer version.

A policy file is TOML with any of the three settings, for example
`examples/policy.toml`, which spells out the defaults.
"""

from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Matching tolerance. Two components, because a flat absolute number treats a
# USD 500 balance and a USD 250,000 one as if they carried the same risk:
#
#   floor  -- sub-unit differences are arithmetic noise at any size. USD 1.00.
#   rate   -- 0.01% of the larger leg, so tolerance scales with the balance.
#
# The effective tolerance is whichever is larger. Sized so genuine FX drift
# still fails: converting the same balance at two rates typically moves it by
# tenths of a percent upward, an order of magnitude past 0.01%.
AMOUNT_TOLERANCE_FLOOR = Decimal("1.00")
AMOUNT_TOLERANCE_RATE = Decimal("0.0001")

# Above this residual an exception is banded HIGH, below it LOW. This is an
# *operational* threshold, not a statutory one, and deliberately much tighter
# than audit materiality would be for a group this size: an intercompany break
# is a signal that a process failed somewhere, and a controller wants to see
# that well before it becomes a misstatement risk. The banding is only an
# input to triage -- it decides nothing on its own.
MATERIALITY_THRESHOLD = Decimal("5000.00")

SETTINGS = ("materiality_threshold", "amount_tolerance_floor", "amount_tolerance_rate")


class PolicyError(ValueError):
    """A policy file that can't be read, or holds a value the close can't use."""


class ClosePolicy(BaseModel):
    """The thresholds one close run applies, and where they came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    materiality_threshold: Decimal = Field(default=MATERIALITY_THRESHOLD, gt=0)
    amount_tolerance_floor: Decimal = Field(default=AMOUNT_TOLERANCE_FLOOR, ge=0)
    amount_tolerance_rate: Decimal = Field(default=AMOUNT_TOLERANCE_RATE, ge=0, lt=1)
    source: str = "built-in defaults"

    def amount_tolerance_for(self, amount: Decimal) -> Decimal:
        """Tolerance applicable to a balance of this size."""
        return max(self.amount_tolerance_floor, abs(amount) * self.amount_tolerance_rate)

    @property
    def tieout_tolerance(self) -> Decimal:
        """Derived from the matching floor rather than set on its own.

        A group that treats a difference as rounding noise when matching one
        balance can't coherently call the same difference a control failure
        when totalling them. The floor is used, not the relative rate -- the
        tie-out compares totals, and a percentage of a total would scale the
        tolerance with the size of the entity's book rather than with the error.
        """
        return self.amount_tolerance_floor

    def describe(self) -> str:
        """One audit-trail line: the policy in force and where it came from."""
        rate = f"{(self.amount_tolerance_rate * 100).normalize():f}%"
        return (
            f"policy ({self.source}): materiality threshold {self.materiality_threshold}; "
            f"matching tolerance the larger of {self.amount_tolerance_floor} and {rate} "
            f"of the larger leg; tie-out tolerance {self.tieout_tolerance}"
        )

    @classmethod
    def from_toml(cls, path: Path) -> ClosePolicy:
        """Read a policy file. Settings it leaves out keep their defaults.

        Decimals are parsed from the file's text, not through a float, so
        0.0001 stays exactly 0.0001.
        """
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh, parse_float=Decimal)
        except OSError as exc:
            raise PolicyError(f"{path}: {exc.strerror or exc}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise PolicyError(f"{path}: not valid TOML ({exc})") from exc

        unknown = sorted(set(raw) - set(SETTINGS))
        if unknown:
            raise PolicyError(
                f"{path}: unknown setting {', '.join(unknown)}; a policy file can set {', '.join(SETTINGS)}"
            )
        try:
            return cls(**raw, source=str(path))
        except ValidationError as exc:
            error = exc.errors()[0]
            raise PolicyError(f"{path}: {error['loc'][0]} {error['msg'].lower()}") from exc


DEFAULT_POLICY = ClosePolicy()
