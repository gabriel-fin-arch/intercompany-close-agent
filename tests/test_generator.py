"""Tests for the synthetic data generator's anomaly injectors."""

from __future__ import annotations

import random

from intercompany_close_agent.synthetic.generator import anomaly_non_interfaced_noise


def _rows(entity: str, counterparty: str, reference: str) -> list[dict]:
    """Two legs of one balance, the shape rows_from_pair produces."""
    return [
        {"entity_code": entity, "counterparty_code": counterparty, "reference": reference},
        {"entity_code": counterparty, "counterparty_code": entity, "reference": reference},
    ]


def test_non_interfaced_noise_rekeys_a_balance_touching_the_manual_entity():
    # ZA01 is the group's one non-interfaced (hand-keyed) entity.
    rows = _rows("ZA01", "US01", "LOAN-INT-2025-1020")
    out = anomaly_non_interfaced_noise(rows, random.Random(0))
    assert out[1]["reference"] == "LOAN_INT-2025-1020"  # hyphen dropped to underscore


def test_non_interfaced_noise_is_a_no_op_between_two_interfaced_entities():
    # Only a hand-keyed entity re-types a reference; interfaced entities load
    # straight from the ERP, so this anomaly must not touch their balances even
    # when the general anomaly pool happens to pick it.
    rows = _rows("US01", "DE01", "ROYALTY-2025-1021")
    out = anomaly_non_interfaced_noise(rows, random.Random(0))
    assert out[1]["reference"] == "ROYALTY-2025-1021"  # unchanged
