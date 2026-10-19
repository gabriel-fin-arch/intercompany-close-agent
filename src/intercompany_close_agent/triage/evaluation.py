"""Triage scored against a known answer: a labelled set and an adversarial one.

Each case in evals/triage/ is a handful of ledger legs and the
classification the close policy gives them. The eval runs the legs through
the matching engine, checks that it raises the one exception the case is
about, classifies that exception with the rules or the model, and passes the
result through `_enforce_taxonomy`, the same exit every close goes through.

Two answers are kept per case. `raw` is what the classifier said; `final` is
what the close would act on. A case passes when `final` is the expected
classification. For the rules the two are always the same. For the model,
the cases where they differ are the ones where the code overruled it, which
is the measure of how far the prompt alone can be trusted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from intercompany_close_agent.matching.engine import match_transactions
from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.policy import DEFAULT_POLICY
from intercompany_close_agent.triage import llm, rules
from intercompany_close_agent.triage.metering import MILLION, PRICES, PRICES_AS_OF, CallRecord
from intercompany_close_agent.triage.models import TriageClassification, TriageJudgment, TriageResult
from intercompany_close_agent.triage.node import _enforce_taxonomy

SETS_DIR = Path("evals") / "triage"
SET_NAMES = ("labelled", "adversarial")
Triage = Literal["rules", "model"]

AUTO = TriageClassification.AUTO_RESOLVABLE
JUDGMENT = TriageClassification.NEEDS_HUMAN_JUDGMENT


class Case(BaseModel):
    id: str
    why: str
    expected_type: ExceptionType
    expected_materiality: Materiality
    expected: TriageClassification
    legs: list[ICTransaction]
    injection: Literal["reference", "currency", "memo"] | None = None


class CaseSet(BaseModel):
    name: str
    description: str
    entities: list[Entity]
    cases: list[Case]

    @property
    def entity_map(self) -> dict[str, Entity]:
        return {entity.code: entity for entity in self.entities}


class CaseSetError(ValueError):
    """A case whose legs don't produce the exception it says they do."""


def set_path(name: str, sets_dir: Path = SETS_DIR) -> Path:
    return sets_dir / f"{name}.json"


def load_set(path: Path) -> CaseSet:
    case_set = CaseSet.model_validate_json(path.read_text(encoding="utf-8"))
    ids = [case.id for case in case_set.cases]
    if len(set(ids)) != len(ids):
        raise CaseSetError(f"{path.name} repeats a case id")
    return case_set


def exception_for(case: Case) -> ICException:
    """The one exception the matching engine raises for this case's legs."""
    result = match_transactions(case.legs, DEFAULT_POLICY)
    if result.clean_pairs or len(result.exceptions) != 1:
        raise CaseSetError(
            f"{case.id}: expected one exception, the engine found {len(result.exceptions)} "
            f"and {len(result.clean_pairs)} clean pair(s)"
        )
    exc = result.exceptions[0]
    if (exc.exception_type, exc.materiality) != (case.expected_type, case.expected_materiality):
        raise CaseSetError(
            f"{case.id}: expected {case.expected_type.value} ({case.expected_materiality.value}), "
            f"the engine raised {exc.exception_type.value} ({exc.materiality.value})"
        )
    return exc


Classifier = Callable[[ICException, dict[str, Entity]], tuple[TriageResult, CallRecord | None]]


def rules_classifier(exc: ICException, entities: dict[str, Entity]) -> tuple[TriageResult, CallRecord | None]:
    return rules.triage_exception(exc, entities), None


def model_classifier(exc: ICException, entities: dict[str, Entity]) -> tuple[TriageResult, CallRecord | None]:
    return llm.triage_measured(exc, entities)


class CaseResult(BaseModel):
    id: str
    exception_type: ExceptionType
    materiality: Materiality
    expected: TriageClassification
    raw: TriageJudgment | None  # what the classifier said; None if its answer didn't parse
    final: TriageClassification | None  # what the close would act on, after _enforce_taxonomy
    overridden: bool = False
    error: str | None = None
    call: CallRecord | None = None

    @property
    def passed(self) -> bool:
        return self.final == self.expected


class EvalRun(BaseModel):
    set_name: str
    triage: Triage
    model: str | None = None
    run_at: str  # UTC, when the run started
    prices_as_of: str | None = None
    cases: list[CaseResult]

    def calls(self) -> list[CallRecord]:
        return [case.call for case in self.cases if case.call is not None]

    @property
    def passed(self) -> int:
        return sum(case.passed for case in self.cases)

    @property
    def raw_agreed(self) -> int:
        return sum(case.raw is not None and case.raw.classification == case.expected for case in self.cases)

    @property
    def unsafe(self) -> list[CaseResult]:
        """Auto-resolved when the policy says a person decides. Must be empty."""
        return [case for case in self.cases if case.final == AUTO and case.expected == JUDGMENT]

    def cost_usd(self) -> Decimal | None:
        calls = self.calls()
        if not calls or any(call.cost_usd is None for call in calls):
            return None
        return sum((call.cost_usd for call in calls if call.cost_usd is not None), Decimal("0"))

    def report(self) -> list[str]:
        who = f"the model ({self.model})" if self.triage == "model" else "the rules"
        total = len(self.cases)
        overridden = sum(case.overridden for case in self.cases)
        lines = [
            f"{self.set_name} set, {who}: {self.passed} of {total} as the policy expects",
            f"  the classifier's own answer: {self.raw_agreed} of {total}; "
            f"overruled by the taxonomy check: {overridden}; "
            f"auto-resolved against the policy: {len(self.unsafe)}",
        ]
        calls = self.calls()
        if calls:
            cost = self.cost_usd()
            priced = f"USD {cost:.4f}" if cost is not None else "cost unknown (no price for the model)"
            seconds = sum(call.seconds for call in calls)
            lines.append(f"  {len(calls)} call(s), {priced} at the prices of {self.prices_as_of}, {seconds:.1f} s")
        for case in self.cases:
            if case.passed:
                continue
            got = case.final.value if case.final else f"no answer ({case.error})"
            raw = f", the classifier said {case.raw.classification.value}" if case.raw else ""
            lines.append(f"  FAIL {case.id}: expected {case.expected.value}, got {got}{raw}")
        return lines


def evaluate(
    case_set: CaseSet, classifier: Classifier, triage: Triage, model: str | None = None
) -> EvalRun:
    """Every case in the set through the classifier and the taxonomy check.

    A set whose legs don't produce what it says raises CaseSetError before
    anything is classified. An answer that doesn't parse is recorded as a
    failed case; any other error from the classifier (a refused key, a
    network failure) stops the run, rather than score the rules under the
    model's name, which is what a close would do.
    """
    exceptions = [exception_for(case) for case in case_set.cases]
    entities = case_set.entity_map
    run_at = datetime.now(UTC).isoformat(timespec="seconds")
    results = []
    for case, exc in zip(case_set.cases, exceptions, strict=True):
        try:
            raw, call = classifier(exc, entities)
        except llm.UnparsedAnswer as err:
            results.append(_unanswered(case, exc, str(err), err.call))
            continue
        except ValidationError as err:
            results.append(_unanswered(case, exc, f"the answer didn't validate: {err.error_count()} error(s)", None))
            continue
        final = _enforce_taxonomy(exc, raw, entities)
        results.append(
            CaseResult(
                id=case.id,
                exception_type=exc.exception_type,
                materiality=exc.materiality,
                expected=case.expected,
                raw=TriageJudgment(**raw.model_dump(exclude={"reference"})),
                final=final.classification,
                overridden=final.classification != raw.classification,
                call=call,
            )
        )
    return EvalRun(
        set_name=case_set.name,
        triage=triage,
        model=model,
        run_at=run_at,
        prices_as_of=PRICES_AS_OF if triage == "model" else None,
        cases=results,
    )


def _unanswered(case: Case, exc: ICException, error: str, call: CallRecord | None) -> CaseResult:
    return CaseResult(
        id=case.id,
        exception_type=exc.exception_type,
        materiality=exc.materiality,
        expected=case.expected,
        raw=None,
        final=None,
        error=error,
        call=call,
    )


def results_path(set_name: str, triage: Triage, model: str | None, sets_dir: Path = SETS_DIR) -> Path:
    """evals/triage/results/<set>/rules.json, or model-<model>.json for the model."""
    label = "rules" if triage == "rules" else f"model-{model}"
    return sets_dir / "results" / set_name / f"{label}.json"


def save(run: EvalRun, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


CHARS_PER_TOKEN = 3


@dataclass(frozen=True)
class Estimate:
    model: str
    calls: int
    input_tokens: int
    output_floor_tokens: int
    output_ceiling_tokens: int
    cost_floor_usd: Decimal
    cost_ceiling_usd: Decimal

    def lines(self, set_name: str) -> list[str]:
        return [
            f"Estimate for {self.model} on the {set_name} set ({self.calls} calls), without calling the API:",
            f"  input   about {self.input_tokens:,} tokens: instructions, output schema and one exception "
            f"a call, at {CHARS_PER_TOKEN} characters a token",
            f"  output  {self.output_floor_tokens:,} to {self.output_ceiling_tokens:,} tokens: from answers the "
            f"length of the rules' own with no thinking, to max_tokens ({llm.MAX_TOKENS:,}) on every call",
            f"  cost    USD {self.cost_floor_usd:.2f} to {self.cost_ceiling_usd:.2f} at the prices of {PRICES_AS_OF}",
        ]


def _tokens(characters: int) -> int:
    return -(-characters // CHARS_PER_TOKEN)


def estimate(case_set: CaseSet, model: str) -> Estimate:
    """Bounds on the tokens and cost of one model run over the set.

    No API call. The input is every prompt the run would send, counted in
    characters, plus the output schema. The output floor is an answer the
    size of the rules' answer for the same case, with no thinking; Opus 5.5
    always thinks, so a real run lands above it. The ceiling is max_tokens on
    every call, which no answer, thinking included, can pass. Both price the
    input as uncached.
    """
    price = PRICES.get(model)
    if price is None:
        raise ValueError(f"no published price for {model} in triage/metering.py")
    entities = case_set.entity_map
    fixed = len(llm.SYSTEM_PROMPT) + len(json.dumps(TriageJudgment.model_json_schema()))
    input_tokens = 0
    floor = 0
    for case in case_set.cases:
        exc = exception_for(case)
        input_tokens += _tokens(fixed + len(llm._describe(exc, entities)))
        answer = rules.triage_exception(exc, entities)
        floor += _tokens(len(TriageJudgment(**answer.model_dump(exclude={"reference"})).model_dump_json()))
    calls = len(case_set.cases)
    ceiling = calls * llm.MAX_TOKENS

    def cost(output_tokens: int) -> Decimal:
        return (input_tokens * price.input + output_tokens * price.output) / MILLION

    return Estimate(
        model=model,
        calls=calls,
        input_tokens=input_tokens,
        output_floor_tokens=floor,
        output_ceiling_tokens=ceiling,
        cost_floor_usd=cost(floor),
        cost_ceiling_usd=cost(ceiling),
    )
