# ADR 0004: Human review as a LangGraph interrupt — nothing is finalized without a decision

- Status: Accepted, 23 October 2026
- Decision owner: Gabriel

## Context

A close that finalizes with undecided items treats "nobody looked at this"
as if it were "someone rejected this" — the same booking outcome, with none
of the accountability. In a real close, an undecided item blocks; it never
silently resolves itself.

## Decision

`human_review` is the only node that can pause the run, implemented with
LangGraph's native `interrupt()` over a checkpointer, not a hand-rolled
flag. If anything needs review, the graph suspends with the pending
worklist; nothing downstream has run. Resuming with the reviewer's
decisions re-enters the graph at exactly the paused point. Every pending
item must carry an explicit decision before the submission is accepted:
approve books an elimination, reject books nothing and is recorded as a
legitimate outcome, and no decision at all means the run does not finalize.
The checkpointer is in-process (`MemorySaver`), which fits a single CLI run
or dashboard session; a persistent one (LangGraph ships a SQLite
checkpointer) can be swapped in without changing any node or edge.

## Alternatives considered

- **Finalize first, review after.** Rejected: review becomes a comment on
  booked entries instead of a control over them.
- **Auto-finalize pending items after a timeout.** Rejected: a clock is not
  a decision-maker.

## Consequences

The pause and the resume are exercised end to end in `tests/test_graph.py`
with no mocking. The dashboard refuses submission until every item is
decided — a rule added after a recording showed an early version booking
undecided items as if approved. Every path leaves a trail: who decided
what, and when.
