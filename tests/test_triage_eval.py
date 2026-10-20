"""Tests for the triage eval: the labelled and adversarial sets, scored offline."""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner

from intercompany_close_agent.cli import app
from intercompany_close_agent.models.exception import ExceptionType, Materiality
from intercompany_close_agent.triage import evaluation, llm
from intercompany_close_agent.triage.evaluation import (
    AUTO,
    JUDGMENT,
    SET_NAMES,
    CaseSetError,
    EvalRun,
    evaluate,
    exception_for,
    load_set,
    results_path,
    rules_classifier,
    set_path,
)
from intercompany_close_agent.triage.metering import CallRecord
from intercompany_close_agent.triage.models import TriageJudgment, TriageResult

ROOT = Path(__file__).resolve().parent.parent
SETS_DIR = ROOT / "evals" / "triage"
runner = CliRunner()


def _set(name: str):
    return load_set(set_path(name, SETS_DIR))


def _always(classification):
    def classifier(exc, entities):
        result = TriageResult(
            reference=exc.reference, classification=classification, confidence=1.0, rationale="always"
        )
        return result, None

    return classifier


@pytest.mark.parametrize("name", SET_NAMES)
def test_every_case_raises_the_exception_it_is_about(name: str):
    for case in _set(name).cases:
        exc = exception_for(case)
        assert (exc.exception_type, exc.materiality) == (case.expected_type, case.expected_materiality)


def test_the_labelled_set_covers_every_type_both_bands_and_a_manual_entity():
    case_set = _set("labelled")
    manual = {entity.code for entity in case_set.entities if not entity.interfaced}
    bands = {(case.expected_type, case.expected_materiality) for case in case_set.cases}
    touching_manual = {
        case.expected_type
        for case in case_set.cases
        if manual & {code for leg in case.legs for code in (leg.entity_code, leg.counterparty_code)}
    }

    assert bands == {(kind, band) for kind in ExceptionType for band in Materiality}
    assert {ExceptionType.AMOUNT_MISMATCH, ExceptionType.TIMING_GAP, ExceptionType.MISSING_COUNTERPARTY} <= (
        touching_manual
    )
    assert all(case.why.strip() for case in case_set.cases)


@pytest.mark.parametrize("name", SET_NAMES)
def test_the_rules_give_every_case_its_expected_classification(name: str):
    run = evaluate(_set(name), rules_classifier, "rules")

    assert run.passed == len(run.cases), run.report()
    assert run.raw_agreed == len(run.cases)
    assert not run.unsafe


@pytest.mark.parametrize("name", SET_NAMES)
def test_the_taxonomy_check_alone_holds_against_a_classifier_that_auto_resolves_everything(name: str):
    """What CI relies on: whatever a prompt talks a classifier into, the
    close never auto-resolves what the policy sends to a person."""
    case_set = _set(name)
    run = evaluate(case_set, _always(AUTO), "model", "compromised")

    assert run.passed == len(run.cases), run.report()
    assert not run.unsafe
    assert sum(case.overridden for case in run.cases) == sum(case.expected == JUDGMENT for case in case_set.cases)


@pytest.mark.parametrize("name", SET_NAMES)
def test_a_classifier_that_escalates_everything_costs_reviews_but_is_never_unsafe(name: str):
    """The direction the check doesn't guard: it never turns an escalation
    into an auto-resolution, so an over-cautious classifier fails exactly the
    cases the policy would have auto-resolved."""
    case_set = _set(name)
    run = evaluate(case_set, _always(JUDGMENT), "model", "cautious")

    assert not run.unsafe
    assert {case.id for case in run.cases if not case.passed} == {
        case.id for case in case_set.cases if case.expected == AUTO
    }


@pytest.mark.parametrize("name", SET_NAMES)
def test_the_saved_rules_runs_match_a_fresh_run(name: str):
    saved = EvalRun.model_validate_json(results_path(name, "rules", None, SETS_DIR).read_text(encoding="utf-8"))
    fresh = evaluate(_set(name), rules_classifier, "rules")

    assert saved.cases == fresh.cases, "re-save with: triage-eval --set NAME --save"


def test_injected_text_reaches_the_prompt_as_one_line_or_not_at_all():
    case_set = _set("adversarial")
    entities = case_set.entity_map

    for case in case_set.cases:
        prompt = llm._describe(exception_for(case), entities)
        keys = [line.split("=")[0].split(":")[0] for line in prompt.splitlines()]
        assert keys[:6] == ["reference", "exception_type", "materiality", "net_amount", "detected_reason", "legs"]
        assert keys[6:] in ([], ["manually_loaded_entities"]), case.id
        if case.injection == "memo":
            for leg in case.legs:
                assert leg.description and leg.description not in prompt, case.id


def test_a_case_whose_legs_raise_something_else_is_refused():
    case = _set("labelled").cases[0].model_copy(update={"expected_type": ExceptionType.TIMING_GAP})

    with pytest.raises(CaseSetError, match="amount-low"):
        exception_for(case)


class _FakeChain:
    """Stands in for prompt | model, returning what include_raw=True returns."""

    def __init__(self, output=None, error: Exception | None = None):
        self.output = output
        self.error = error
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.output


def _usage(input_tokens: int, output_tokens: int, cache_read: int = 0) -> AIMessage:
    return AIMessage(
        content="",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cache_read},
        },
    )


def test_the_model_path_records_the_cost_and_latency_of_every_call(monkeypatch):
    judgment = TriageJudgment(classification=AUTO, confidence=0.9, rationale="from the fake model")
    chain = _FakeChain({"raw": _usage(1200, 150), "parsed": judgment, "parsing_error": None})
    monkeypatch.setattr(llm, "_build_chain", lambda include_raw=False: chain)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    case_set = _set("adversarial")

    run = evaluate(case_set, evaluation.model_classifier, "model", llm.model_name())

    assert chain.calls == len(case_set.cases)
    assert all(case.call is not None and case.call.seconds >= 0 for case in run.cases)
    # 1,200 input tokens at USD 4 and 150 output at USD 20, per million
    assert {case.call.cost_usd for case in run.cases if case.call} == {Decimal("0.007800")}
    assert run.cost_usd() == Decimal("0.007800") * len(case_set.cases)
    assert not run.unsafe, "an auto-resolving model is still overruled"
    assert "USD" in "\n".join(run.report())


def test_an_answer_that_does_not_parse_fails_the_case_and_keeps_its_cost(monkeypatch):
    chain = _FakeChain({"raw": _usage(1000, 40), "parsed": None, "parsing_error": ValueError("not JSON")})
    monkeypatch.setattr(llm, "_build_chain", lambda include_raw=False: chain)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5-5")

    run = evaluate(_set("adversarial"), evaluation.model_classifier, "model", llm.model_name())

    assert run.passed == 0
    assert all(case.final is None and "not JSON" in (case.error or "") for case in run.cases)
    assert all(case.call is not None and case.call.output_tokens == 40 for case in run.cases)


def test_any_other_model_error_stops_the_run(monkeypatch):
    """A refused key would otherwise fail every case one by one, or worse,
    fall back to the rules and be scored as the model."""
    chain = _FakeChain(error=RuntimeError("401 invalid x-api-key"))
    monkeypatch.setattr(llm, "_build_chain", lambda include_raw=False: chain)

    with pytest.raises(RuntimeError, match="401"):
        evaluate(_set("labelled"), evaluation.model_classifier, "model", llm.model_name())
    assert chain.calls == 1


def test_call_records_split_out_the_cache_and_cost_unknown_models_as_unknown():
    usage = {
        "input_tokens": 1000,
        "output_tokens": 200,
        "input_token_details": {"cache_read": 600, "cache_creation": 100},
    }
    call = CallRecord.from_usage(usage, "claude-opus-5", 1.23456)

    assert (call.input_tokens, call.cache_read_input_tokens, call.cache_creation_input_tokens) == (300, 600, 100)
    # 300 x 5 + 100 x 6.25 + 600 x 0.50 + 200 x 25, per million
    assert call.cost_usd == Decimal("0.007425")
    assert call.seconds == 1.235
    assert CallRecord.from_usage(usage, "some-model", 1.0).cost_usd is None
    assert CallRecord.from_usage(None, "claude-opus-5-5", 1.0).input_tokens == 0


def test_the_estimate_prices_the_set_without_calling_the_api(monkeypatch):
    monkeypatch.setattr(llm, "_build_chain", lambda include_raw=False: pytest.fail("no call in an estimate"))
    case_set = _set("labelled")

    estimate = evaluation.estimate(case_set, "claude-opus-5-5")

    assert estimate.calls == len(case_set.cases)
    assert 0 < estimate.output_floor_tokens < estimate.output_ceiling_tokens == len(case_set.cases) * llm.MAX_TOKENS
    assert 0 < estimate.cost_floor_usd < estimate.cost_ceiling_usd < Decimal("10")
    with pytest.raises(ValueError, match="no published price"):
        evaluation.estimate(case_set, "some-model")


def test_the_cli_scores_a_set_and_saves_the_run(tmp_path: Path):
    shutil.copy(SETS_DIR / "labelled.json", tmp_path / "labelled.json")

    result = runner.invoke(app, ["triage-eval", "--set", "labelled", "--save", "--sets-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "24 of 24 as the policy expects" in result.output
    saved = json.loads((tmp_path / "results" / "labelled" / "rules.json").read_text(encoding="utf-8"))
    assert (saved["triage"], saved["model"], len(saved["cases"])) == ("rules", None, 24)


def test_the_cli_exits_1_when_a_case_misses(tmp_path: Path):
    data = json.loads((SETS_DIR / "labelled.json").read_text(encoding="utf-8"))
    data["cases"][0]["expected"] = "needs_human_judgment"
    (tmp_path / "labelled.json").write_text(json.dumps(data), encoding="utf-8")

    result = runner.invoke(app, ["triage-eval", "--sets-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "FAIL amount-low: expected needs_human_judgment, got auto_resolvable" in result.output


def test_the_cli_model_path_needs_a_key_and_the_estimate_does_not(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    refused = runner.invoke(app, ["triage-eval", "--triage", "model"])
    estimated = runner.invoke(app, ["triage-eval", "--triage", "model", "--estimate", "--set", "adversarial"])

    assert refused.exit_code == 1
    assert "needs ANTHROPIC_API_KEY" in refused.output
    assert estimated.exit_code == 0, estimated.output
    assert "Estimate for claude-opus-5-5 on the adversarial set (11 calls)" in estimated.output


def test_the_cli_refuses_an_unknown_set():
    result = runner.invoke(app, ["triage-eval", "--set", "test"])

    assert result.exit_code == 2
    assert "labelled or adversarial" in result.output


def test_the_doc_states_what_the_estimate_prints():
    doc = (ROOT / "docs" / "triage-eval.md").read_text(encoding="utf-8")

    for name in SET_NAMES:
        case_set = _set(name)
        estimate = evaluation.estimate(case_set, llm.DEFAULT_MODEL)
        row = (
            f"| {name} | {estimate.calls} | about {estimate.input_tokens:,} tokens | "
            f"{estimate.output_floor_tokens:,} to {estimate.output_ceiling_tokens:,} tokens | "
            f"USD {estimate.cost_floor_usd:.2f} to {estimate.cost_ceiling_usd:.2f} |"
        )
        assert row in doc, row
        rules_run = evaluate(case_set, rules_classifier, "rules")
        total = len(rules_run.cases)
        assert f"| {name} ({total}) | rules | {rules_run.passed} | {rules_run.raw_agreed} | 0 | 0 |" in doc


@pytest.mark.parametrize("name", SET_NAMES)
def test_the_saved_model_run_is_what_the_doc_reports(name: str):
    """The 20 October run of Claude Opus 5.5: still the set it was run on, every
    call costed, never auto-resolved against the policy, and the doc's tables
    are its numbers."""
    run = EvalRun.model_validate_json(
        results_path(name, "model", "claude-opus-5-5", SETS_DIR).read_text(encoding="utf-8")
    )
    case_set = _set(name)
    doc = (ROOT / "docs" / "triage-eval.md").read_text(encoding="utf-8")
    calls = run.calls()

    assert [(case.id, case.expected) for case in run.cases] == [(case.id, case.expected) for case in case_set.cases]
    assert len(calls) == len(run.cases) and all(call.cost_usd is not None for call in calls)
    assert not run.unsafe
    overridden = sum(case.overridden for case in run.cases)
    results_row = (
        f"| {name} ({len(run.cases)}) | Claude Opus 5.5 | {run.passed} | {run.raw_agreed} | {overridden} | 0 |"
    )
    assert results_row in doc, results_row
    tokens_in = sum(c.input_tokens + c.cache_read_input_tokens + c.cache_creation_input_tokens for c in calls)
    tokens_out = sum(call.output_tokens for call in calls)
    seconds = sum(call.seconds for call in calls)
    longest = max(call.seconds for call in calls)
    row = (
        f"| {name} | {len(calls)} | {tokens_in:,} | {tokens_out:,} | {run.cost_usd():.2f} | {seconds:.1f} | "
        f"{longest:.1f} s |"
    )
    assert row in doc, row
