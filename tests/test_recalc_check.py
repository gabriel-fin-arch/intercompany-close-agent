"""The reconciliation of recalc/ic_recalc.sql against the pipeline (recalc_check.py).

CI runs the check itself, on the accountant's SQL, in its own job. These tests
hold the comparison to what it promises: every entity, reference or total that
differs is reported, and nothing that agrees is.
"""

from dataclasses import replace
from decimal import Decimal

from intercompany_close_agent.recalc_check import (
    Figures,
    Pair,
    TieOut,
    differences,
    from_pipeline,
    report,
)


def _figures() -> Figures:
    return Figures(
        tieout={
            "DE01": TieOut(Decimal("100.00"), Decimal("100.00"), Decimal("0.00"), False),
            "US01": TieOut(Decimal("-50.00"), Decimal("-40.00"), Decimal("-10.00"), True),
        },
        pairs={"REF-1": Pair("clean", None), "REF-2": Pair("exception", "timing_gap")},
        eliminated=Decimal("1000.00"),
    )


def _found(recalc: Figures, pipeline: Figures) -> list[tuple[str, object, object]]:
    return [(d.where, d.recalc, d.pipeline) for d in differences(recalc, pipeline)]


def test_two_sides_that_agree_have_no_differences():
    assert differences(_figures(), _figures()) == []


def test_a_tie_out_that_differs_is_named_by_entity_and_field():
    recalc = _figures()
    recalc.tieout["US01"] = replace(recalc.tieout["US01"], is_break=False)
    assert _found(recalc, _figures()) == [("tie-out, US01, is_break", False, True)]


def test_an_entity_on_one_side_only_is_a_difference():
    recalc = _figures()
    del recalc.tieout["DE01"]
    assert _found(recalc, _figures()) == [("tie-out, DE01", "missing", "present")]


def test_a_reference_that_differs_in_outcome_or_type_is_reported():
    recalc = _figures()
    recalc.pairs["REF-1"] = Pair("exception", "amount_mismatch")
    recalc.pairs["REF-2"] = Pair("exception", "amount_mismatch")
    recalc.pairs["REF-3"] = Pair("clean", None)
    assert _found(recalc, _figures()) == [
        ("pairs, REF-1, outcome", "exception", "clean"),
        ("pairs, REF-2, exception type", "amount_mismatch", "timing_gap"),
        ("pairs, REF-3", "present", "missing"),
    ]


def test_the_type_is_compared_only_when_the_recalculation_gives_one():
    recalc = _figures()
    recalc.pairs["REF-2"] = Pair("exception", None)
    assert differences(recalc, _figures()) == []


def test_a_different_eliminated_total_is_reported():
    recalc = replace(_figures(), eliminated=Decimal("999.99"))
    assert _found(recalc, _figures()) == [("eliminated, clean pairs", Decimal("999.99"), Decimal("1000.00"))]


def test_the_report_lists_each_difference_or_says_there_are_none():
    agree = report(_figures(), _figures(), [])
    assert agree[-1].startswith("No differences: 2 entities, 2 references")

    recalc = replace(_figures(), eliminated=Decimal("1234567.89"))
    lines = report(recalc, _figures(), differences(recalc, _figures()))
    assert "**1 difference(s).**" in lines[-5]
    assert lines[-1] == "| eliminated, clean pairs | 1,234,567.89 | 1,000.00 |"


def test_the_pipeline_side_on_the_sample_data(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    figures = from_pipeline()
    assert {e: t.variance for e, t in figures.tieout.items() if t.is_break} == {"US01": Decimal("-2536.01")}
    assert len(figures.tieout) == 7
    assert sum(p.outcome == "clean" for p in figures.pairs.values()) == 11
    assert sum(p.outcome == "exception" for p in figures.pairs.values()) == 18
    assert figures.eliminated == Decimal("1465943.91")
