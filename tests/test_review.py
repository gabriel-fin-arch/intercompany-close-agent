"""Tests for reviewer-decision parsing helpers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from intercompany_close_agent.models.review import parse_override_amount


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_override_means_no_override(blank):
    assert parse_override_amount(blank) is None


def test_valid_amount_is_parsed_and_stripped():
    assert parse_override_amount("  1234.56 ") == Decimal("1234.56")


@pytest.mark.parametrize("bad", ["abc", "1,234.56", "$500", "12.3.4"])
def test_unparseable_amount_raises_a_clear_error(bad):
    with pytest.raises(ValueError, match="must be a number"):
        parse_override_amount(bad)


@pytest.mark.parametrize("bad", ["0", "-500.00"])
def test_non_positive_amount_is_rejected(bad):
    with pytest.raises(ValueError, match="must be a positive number"):
        parse_override_amount(bad)
