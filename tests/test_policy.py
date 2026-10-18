"""Tests for the close policy and reading it from a file."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from intercompany_close_agent.policy import (
    AMOUNT_TOLERANCE_FLOOR,
    AMOUNT_TOLERANCE_RATE,
    DEFAULT_POLICY,
    MATERIALITY_THRESHOLD,
    ClosePolicy,
    PolicyError,
)

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "policy.toml"


def _policy_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "policy.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_defaults_are_the_values_the_close_has_always_used():
    assert DEFAULT_POLICY.materiality_threshold == MATERIALITY_THRESHOLD == Decimal("5000.00")
    assert DEFAULT_POLICY.amount_tolerance_floor == AMOUNT_TOLERANCE_FLOOR == Decimal("1.00")
    assert DEFAULT_POLICY.amount_tolerance_rate == AMOUNT_TOLERANCE_RATE == Decimal("0.0001")
    assert DEFAULT_POLICY.tieout_tolerance == AMOUNT_TOLERANCE_FLOOR


def test_the_example_file_spells_out_the_defaults():
    example = ClosePolicy.from_toml(EXAMPLE)

    assert example.model_dump(exclude={"source"}) == DEFAULT_POLICY.model_dump(exclude={"source"})
    assert example.source == str(EXAMPLE)


def test_a_setting_left_out_keeps_its_default(tmp_path: Path):
    policy = ClosePolicy.from_toml(_policy_file(tmp_path, "materiality_threshold = 25000\n"))

    assert policy.materiality_threshold == Decimal("25000")
    assert policy.amount_tolerance_floor == AMOUNT_TOLERANCE_FLOOR
    assert policy.amount_tolerance_rate == AMOUNT_TOLERANCE_RATE


def test_decimals_are_read_from_the_text_not_through_a_float(tmp_path: Path):
    """0.1 as a float is 0.1000000000000000055...; a tolerance is compared to
    money, so it has to be exactly what the file says."""
    policy = ClosePolicy.from_toml(_policy_file(tmp_path, "amount_tolerance_rate = 0.1\n"))

    assert policy.amount_tolerance_rate == Decimal("0.1")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("materiality = 5000\n", "unknown setting materiality"),
        ("source = 'mine'\n", "unknown setting source"),
        ("materiality_threshold = 0\n", "materiality_threshold input should be greater than 0"),
        ("amount_tolerance_floor = -1\n", "amount_tolerance_floor input should be greater than or equal to 0"),
        ("amount_tolerance_rate = 1.5\n", "amount_tolerance_rate input should be less than 1"),
        ("materiality_threshold = 'a lot'\n", "materiality_threshold"),
        ("materiality_threshold = \n", "not valid TOML"),
    ],
)
def test_a_policy_the_close_cannot_use_is_refused_with_the_file_named(tmp_path: Path, text: str, message: str):
    path = _policy_file(tmp_path, text)

    with pytest.raises(PolicyError, match=message) as raised:
        ClosePolicy.from_toml(path)

    assert str(raised.value).startswith(str(path))


def test_a_missing_policy_file_is_a_policy_error(tmp_path: Path):
    with pytest.raises(PolicyError, match="nope.toml"):
        ClosePolicy.from_toml(tmp_path / "nope.toml")


def test_the_policy_describes_itself_for_the_audit_trail(tmp_path: Path):
    policy = ClosePolicy.from_toml(_policy_file(tmp_path, "amount_tolerance_rate = 0.0005\n"))

    assert policy.describe() == (
        f"policy ({tmp_path / 'policy.toml'}): materiality threshold 5000.00; matching tolerance the "
        "larger of 1.00 and 0.05% of the larger leg; tie-out tolerance 1.00"
    )
