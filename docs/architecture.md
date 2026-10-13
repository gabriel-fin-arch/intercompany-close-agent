# Architecture

## The graph

```
        START
          |
        ingest
          |
      reconcile  ---------------- reconciliation/tieout.py (deterministic)
          |
        match  ------------------- matching/engine.py (deterministic)
          |
        triage ------------------- triage/llm.py or triage/rules.py
          |
     human_review ---------------- interrupt() here, if anything needs it
          |
       finalize ------------------ eliminations/engine.py (deterministic)
          |
         END
```

Implemented as a LangGraph `StateGraph` (`graph/graph.py`) over `CloseState`
(`graph/state.py`), a `TypedDict` that every node reads in full and returns
a partial update for. There's no custom reducer on state fields; nodes that
append to `audit_trail` read the current list and return the whole new list
themselves. For a project this size that's simpler to follow than
`Annotated[list, operator.add]`, and it's explicit about what each node
actually changed.

## Reconcile before you eliminate

`reconcile` runs before any matching and answers a question matching can't:
does the intercompany subledger agree with what each entity's general
ledger says its intercompany position is? It sums every entity's IC legs
and compares that to the entity's `IC_RECEIVABLE` + `IC_PAYABLE` control
accounts on the trial balance.

The distinction matters. A single balance failing to match its counterparty
is a reconciliation item; someone chases one transaction. A control
account that doesn't tie means the subledger and the GL disagree about the
*totals*, so every elimination built off that subledger is suspect. That's
worth knowing before the run starts, not after it produces entries.

It deliberately does **not** trip the `human_review` interrupt. A tie-out
break is an entity-level data problem for someone to chase offline, not a
per-balance judgment call, so routing it into the reviewer worklist would
mix two different kinds of work. It's reported in the audit trail, carried
in state as `tb_variances`, and surfaced by both the CLI and the dashboard.

## The thresholds, and why they're set where they are

Every number in `matching/engine.py` and `triage/rules.py` is a judgment
call. None of them is a standard. What follows is the reasoning, so a
reviewer can disagree with the values without having to reverse-engineer
the intent.

**Matching tolerance is two numbers, not one.** A flat absolute tolerance
treats a USD 500 balance and a USD 250,000 one as if they carried the same
risk. So the tolerance is the larger of a floor (USD 1.00, because sub-unit
differences are arithmetic noise at any size) and a rate (0.01% of the
larger leg). The rate is deliberately an order of magnitude below real FX
drift: converting the same balance at two different rates typically moves
it by tenths of a percent, so a genuine FX difference still fails the check
rather than being absorbed by it. `tests/test_matching.py` asserts exactly
that.

**Materiality is operational, not statutory.** For a group this size, audit
materiality would run into the millions and a "clearly trivial" threshold
into the tens of thousands. The threshold here (USD 5,000) is far tighter on
purpose: an intercompany break is a signal that a process failed somewhere,
and a controller wants to see that long before it becomes a misstatement
risk. Using an audit-derived number here would be technically defensible and
operationally useless.

**Materiality means different things per exception type, deliberately.** For
an amount mismatch or a duplicate reference it bands the *net of the legs
sharing that reference*; for a missing counterparty, a counterparty
mismatch, self-dealing, a currency mismatch, or a timing gap it bands the
*balance at risk* (the larger leg), because in those cases the residual
isn't the interesting number: the whole balance is what's in question.

**The tie-out tolerance is derived, not chosen.** It reuses the matching
floor, because a group that calls a difference rounding noise when matching
one balance can't coherently call the same difference a control failure when
totalling them. It uses the floor rather than the rate: this compares totals,
and a percentage of a total would scale the tolerance with the size of the
entity's book instead of with the error.

**Confidence values are bands, not probabilities.** See
`docs/human-in-the-loop.md`.

## Why matching and exception detection are one node, not two

`matching/engine.py`'s `match_transactions()` is a single pure function: it
groups transaction legs by reference and, for each group, either produces a
clean pair or an `ICException`. There's no meaningful boundary to split
that into two graph nodes without inventing a hand-off of the same data
between them, so the `match` node calls it once and stores both outputs
(`clean_pairs` and `exceptions`) in state. Splitting it would have padded
the graph without changing what it does.

## State shape

```python
class CloseState(TypedDict, total=False):
    entities: list[Entity]
    trial_balance: list[TrialBalanceLine]
    ic_transactions: list[ICTransaction]

    tb_variances: list[TrialBalanceVariance]

    clean_pairs: list[tuple[ICTransaction, ICTransaction]]
    exceptions: list[ICException]

    triage_results: list[TriageResult]

    review_decisions: list[ReviewDecision]
    eliminations: list[Elimination]

    audit_trail: list[str]
```

`entities` / `trial_balance` / `ic_transactions` are populated by the
caller (CLI or dashboard) before the graph runs. The `ingest` node exists
so the pipeline's shape says explicitly "this is where a real system would
hit the source files or APIs," even though in this project the loading
already happened by the time `invoke()` is called.

## The LLM does not do arithmetic

Two things are true about every number that ends up in an elimination
entry:

1. It was computed by deterministic Python in `matching/` or
   `eliminations/`, both fully unit tested, including a net-zero invariant
   enforced as a pydantic model validator on `Elimination`.
2. No LLM call ever sees a number and is asked to do anything with it other
   than read it as context.

`triage/llm.py` and `triage/rules.py` both implement one contract: given an
`ICException`, return a `TriageResult` (`classification`,
`confidence`, `rationale`). Neither one touches `net_amount` or produces an
amount. When `finalize` (`graph/nodes.py`) builds an elimination for an
`auto_resolvable` exception, it pulls the amount straight from the
exception's own legs, not from anything triage returned. The LLM's entire
job is: is this safe to auto-resolve, and if a human needs to look at it,
what should they know first.

## Triage dispatch and graceful degradation

`triage/node.py` is the one place that decides which triage implementation
runs:

```python
def triage_exception(exc, entities=None) -> TriageResult:
    if _llm_is_configured():
        try:
            return _enforce_taxonomy(exc, llm_triage(exc, entities), entities)
        except Exception:
            return _enforce_taxonomy(exc, rules_triage(exc, entities), entities)   # network blip, rate limit, bad shape...
    return _enforce_taxonomy(exc, rules_triage(exc, entities), entities)
```

A live model call failing mid-run doesn't take the close down. It falls
back to the same deterministic rules used when no API key is configured at
all. This is also what makes the offline mode more than a demo convenience:
it's the same code path a flaky network hits in production.

Note that neither branch returns a classifier's output directly --
`_enforce_taxonomy` always sits between the classifier and the caller. See
"The auto-resolve policy is re-checked in code" below.

## The auto-resolve policy is re-checked in code

Three things have to be true for an exception to be auto-resolved:

1. its type isn't one of the six in `ALWAYS_NEEDS_JUDGMENT`,
2. the amount at stake is immaterial -- the residual, or for a timing gap
   the whole balance, and
3. no entity on either side of the balance is manually loaded.

All three are stated in `triage/llm.py`'s system prompt for the live model,
and all three are implemented directly in `triage/rules.py` for the offline
fallback. But `_enforce_taxonomy` (`triage/node.py`) re-checks all three
again, in code, on whatever either path returns -- it isn't only the
taxonomy that's reguarded there, despite the function's name surviving from
before the other two checks were added.

That matters because a prompt is a request, not a guarantee: an
intercompany reference is free text typed by whoever submitted the balance,
and it lands inside the prompt verbatim, so a reference carrying an
instruction -- or a live model simply being wrong about materiality or an
entity's data quality -- could return `auto_resolvable` for something that
must never be. `_enforce_taxonomy` runs after the classifier either way, so
nothing that arrives through a prompt can reach it. If the classifier
disagrees with any part of the policy, the policy wins, and the override is
recorded in the rationale the reviewer reads, alongside what the classifier
originally said. See `tests/test_triage_node.py` for the cases this pins
down, including a compromised-model test for each of the three checks.

## The interrupt

`human_review` (`graph/nodes.py`) is the only node that can pause the
entire run. If nothing needs review, it's a no-op: `interrupt()` is never
called, and the graph flows straight to `finalize`. If something does:

```python
decisions_payload = interrupt({"pending_review": pending})
```

This suspends the whole graph. `run_close()` (`graph/graph.py`) returns
with `"__interrupt__"` in the result, carrying the pending worklist. Nothing
downstream of `human_review` has run yet. Resuming:

```python
compiled.invoke(Command(resume=decisions), config=config)
```

re-enters the graph at exactly the paused point, `interrupt()` returns
`decisions` as its value, and execution continues into `finalize`. This is
LangGraph's native interrupt mechanism (backed by a checkpointer), not a
hand-rolled pause flag. See `tests/test_graph.py` for the real
interrupt/resume cycle exercised end to end, no mocking.

**Checkpointer:** `MemorySaver`, in-process only. That's the right choice
for this project's scope: a single CLI run or a single Streamlit session,
where the pause and the resume happen in the same process. A version that
needed to survive a process restart between pause and resume (e.g. a
reviewer coming back the next day) would swap in a persistent checkpointer
(LangGraph ships a SQLite one); nothing about the graph's nodes or edges
would need to change.

## Finalize: three paths to an elimination

`finalize` builds the elimination set in three passes:

1. **Clean pairs**, straight through `eliminations.engine.build_eliminations()`.
2. **Auto-resolvable exceptions**, via `build_elimination_from_exception()`,
   using the exception's own two legs.
3. **Human-approved exceptions**, same function, but only after an
   `approve` or `edit` decision exists for that reference. A `reject`
   decision, or no decision at all (still pending), produces no
   elimination.

One case needed its own function: a `MISSING_COUNTERPARTY` exception has
only one leg, so there's no second leg to derive an amount from even after
a human approves it. `build_elimination_from_known_leg()` handles that path.
It requires the reviewer to supply the amount (`ReviewDecision.override_amount`)
and books it against the counterparty the known leg already names. This was
found by the end-to-end graph tests, not designed up front: an early
version of `finalize` called the two-leg function unconditionally and blew
up on the first approved missing-counterparty case in the real synthetic
dataset. See `tests/test_graph.py` and the `eliminations: support
human-approved bookings with no counterparty leg` commit.

A second case needed its own routing for the opposite reason: a
`SIGN_MISMATCH` exception has two legs, but they point the same way, so
there's no unambiguous receivable/payable pair to build an entry from
either. `finalize` routes it around `build_elimination_from_exception`
entirely and records that it needs manual resolution instead.

## An elimination can still leave a residual, and that's reported, not hidden

`build_elimination_from_exception()` books at the receivable leg's own
amount by default (or a reviewer's override) -- not the residual, and not
something in between. When that amount doesn't match what the *other*
entity actually booked (an `AMOUNT_MISMATCH` residual that was auto-resolved
below materiality, or a human approval with no override), the payable
side's control account won't net to zero after the entry posts. That's the
same category of problem `reconcile` checks for before matching starts,
just introduced by the elimination itself instead of by the original
booking.

`eliminations.engine.elimination_residuals()` computes it -- per entity, the
difference between what that entity's leg said and what actually got posted
against its control account -- and `finalize` appends a line to
`audit_trail` for every nonzero one it finds:

```
ROYALTY-2025-1001: eliminated at 246809.45, but GB01's control account
carries an unexplained residual of 3085.12 after posting
```

This doesn't fix the underlying gap -- there's no honest way to invent the
correct number from two disagreeing legs -- but it means the gap shows up
next to the elimination that caused it, instead of only turning up the next
time someone runs a tie-out and wonders why a balance that was supposedly
eliminated still isn't zero. See `tests/test_eliminations.py` and
`tests/test_graph.py::test_finalize_surfaces_a_control_account_residual_left_by_an_elimination`.

Clean pairs get the same treatment. "Clean" means the legs net to within
tolerance, not to zero, and the entry is built the same way, so the payable
side can keep a difference of up to the tolerance -- 0.02 on
`MGMT-FEE-2025-1006` in the sample data:

```
MGMT-FEE-2025-1006: matched within tolerance and eliminated at 41780.79;
US01's control account keeps a residual of -0.02 after posting
```

Writing that off is a policy decision for the group, not something this
code should do on its own; recording it is the part that isn't optional.
