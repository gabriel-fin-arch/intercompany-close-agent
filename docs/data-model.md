# Data model

All models are pydantic v2 (`src/intercompany_close_agent/models/`, plus
`triage/models.py` for the triage-specific ones). Money is `Decimal`
throughout -- `float` has no business anywhere near a balance that has to
net to exactly zero.

## Master data

**`Entity`** (`models/entity.py`) -- a legal entity in the group. The
`interfaced` flag matters more than it looks: a non-interfaced entity's
data is manually loaded, which is exactly where reference typos and
re-keying slips creep in (see `data/synthetic/README.md`).

## Ledger data

**`TrialBalanceLine`** / **`ICTransaction`** (`models/ledger.py`) -- the
two feeds the pipeline ingests. An `ICTransaction` is one *leg* of an
intercompany balance, as booked by a single entity; a clean balance has
exactly two legs (one per side) that net to zero.

## Reconciliation output

**`TrialBalanceVariance`** (`models/control.py`) -- one entity's
intercompany position as the subledger sees it, next to what its trial
balance control accounts say. Produced by the `reconcile` node before any
matching happens. `within_tolerance` is precomputed rather than left to the
caller, so the CLI, the dashboard and the audit trail can't disagree about
what counts as a break.

## Matching output

**`ICException`** (`models/exception.py`) -- what's left over once clean
pairs are pulled out. Deliberately free of anything an LLM produces: no
confidence score, no narrative. Whether triage runs against Claude or the
offline rule fallback, an `ICException` means the same thing either way:
the matching engine that builds it never knows or cares which one is
coming next.

```python
class ICException(BaseModel):
    reference: str
    exception_type: ExceptionType   # missing_counterparty | counterparty_mismatch
                                    # | self_dealing | currency_mismatch | sign_mismatch
                                    # | amount_mismatch | timing_gap | duplicate_reference
    legs: list[ICTransaction]
    net_amount: Decimal | None      # None for currency_mismatch -- nothing to sum
                                    # across currencies without an FX rate
    materiality: Materiality        # low | high: pure magnitude, not a judgment call
    detected_reason: str            # plain-language, code-generated
```

## Triage output

**`TriageJudgment`** / **`TriageResult`** (`triage/models.py`) -- what
triage decides about one exception. `TriageJudgment` is the bare judgment
(classification, confidence, rationale); `TriageResult` adds the
`reference` back on. Split this way so the LLM's structured-output schema
(`TriageJudgment`) never has to correctly echo back a reference string.
The code sets that itself from the exception being triaged.

```python
class TriageJudgment(BaseModel):
    classification: TriageClassification  # auto_resolvable | needs_human_judgment
    confidence: float                     # 0.0-1.0
    rationale: str

class TriageResult(TriageJudgment):
    reference: str
```

## Review output

**`ReviewDecision`** (`models/review.py`) -- a human reviewer's decision on
one exception. `reviewer` is required: every decision says who made it, and
`finalize` won't book one made by whoever prepared the run.
`override_amount` is only meaningful for `action=edit`, and `decided_at`
defaults to the current UTC time so every decision carries its own timestamp
without the caller having to remember to set one.

```python
class ReviewDecision(BaseModel):
    reference: str
    action: ReviewAction              # approve | reject | edit
    reviewer: str                     # typed in, not authenticated
    reviewer_note: str = ""
    override_amount: Decimal | None = None
    decided_at: datetime
```

## Elimination output

**`Elimination`** / **`JournalLine`** (`models/elimination.py`) -- the
final output. Balance is enforced at the model level, not just checked
after the fact:

```python
class Elimination(BaseModel):
    reference: str
    lines: list[JournalLine]
    narrative: str = ""

    @model_validator(mode="after")
    def _check_balances(self) -> Elimination:
        ...  # raises ValueError if debits != credits
```

Constructing an `Elimination` with unbalanced lines is a validation error,
not a possible runtime state -- see `tests/test_eliminations.py::test_elimination_model_rejects_unbalanced_lines`.

## How they connect

```
ICTransaction (x2, one per leg)
      |
      | matching/engine.py
      v
clean pair ---------------------> eliminations/engine.py -> Elimination
      |
      | (doesn't match cleanly)
      v
  ICException
      |
      | triage/{llm,rules}.py
      v
 TriageResult
      |
      +-- auto_resolvable -------> eliminations/engine.py -> Elimination
      |
      +-- needs_human_judgment --> human_review (interrupt) --> ReviewDecision
                                          |
                                          +-- approve/edit --> eliminations/engine.py -> Elimination
                                          +-- reject -------> no elimination
```
