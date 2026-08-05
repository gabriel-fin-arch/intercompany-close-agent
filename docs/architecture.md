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
is a reconciliation item -- someone chases one transaction. A control
account that doesn't tie means the subledger and the GL disagree about the
*totals*, so every elimination built off that subledger is suspect. That's
worth knowing before the run starts, not after it produces entries.

It deliberately does **not** trip the `human_review` interrupt. A tie-out
break is an entity-level data problem for someone to chase offline, not a
per-balance judgment call, so routing it into the reviewer worklist would
mix two different kinds of work. It's reported in the audit trail, carried
in state as `tb_variances`, and surfaced by both the CLI and the dashboard.

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
caller (CLI or dashboard) before the graph runs -- the `ingest` node exists
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

`triage/llm.py` and `triage/rules.py` both implement the same contract --
given an `ICException`, return a `TriageResult` (`classification`,
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
def triage_exception(exc: ICException) -> TriageResult:
    if _llm_is_configured():
        try:
            return llm_triage(exc)
        except Exception:
            return rules_triage(exc)   # network blip, rate limit, bad response shape...
    return rules_triage(exc)
```

A live model call failing mid-run doesn't take the close down -- it falls
back to the same deterministic rules used when no API key is configured at
all. This is also what makes the offline mode more than a demo convenience:
it's the same code path a flaky network hits in production.

## The interrupt

`human_review` (`graph/nodes.py`) is the only node that can pause the
entire run. If nothing needs review, it's a no-op -- `interrupt()` is never
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
hand-rolled pause flag -- see `tests/test_graph.py` for the real
interrupt/resume cycle exercised end to end, no mocking.

**Checkpointer:** `MemorySaver`, in-process only. That's the right choice
for this project's scope -- a single CLI run or a single Streamlit session,
where the pause and the resume happen in the same process. A version that
needed to survive a process restart between pause and resume (e.g. a
reviewer coming back the next day) would swap in a persistent checkpointer
(LangGraph ships a SQLite one); nothing about the graph's nodes or edges
would need to change.

## Finalize: three paths to an elimination

`finalize` builds the elimination set in three passes:

1. **Clean pairs** -- straight through `eliminations.engine.build_eliminations()`.
2. **Auto-resolvable exceptions** -- `build_elimination_from_exception()`,
   using the exception's own two legs.
3. **Human-approved exceptions** -- same function, but only after an
   `approve` or `edit` decision exists for that reference. A `reject`
   decision, or no decision at all (still pending), produces no
   elimination.

One case needed its own function: a `MISSING_COUNTERPARTY` exception has
only one leg, so there's no second leg to derive an amount from even after
a human approves it. `build_elimination_from_known_leg()` handles that path
-- it requires the reviewer to supply the amount (`ReviewDecision.override_amount`)
and books it against the counterparty the known leg already names. This
was found by the end-to-end graph tests, not designed up front: an early
version of `finalize` called the two-leg function unconditionally and blew
up on the first approved missing-counterparty case in the real synthetic
dataset. See `tests/test_graph.py` and the `eliminations: support
human-approved bookings with no counterparty leg` commit.
