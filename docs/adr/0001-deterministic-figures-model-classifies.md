# ADR 0001: Figures are deterministic; the model only classifies and explains

- Status: Accepted, 23 October 2026
- Decision owner: Gabriel

## Context

The pipeline books elimination entries with real amounts. A language model
could, in principle, compute those amounts — and would get them right most
of the time. "Most of the time" is not a bar an elimination entry can meet:
a wrong amount that posts is a misstatement, not a bug.

## Decision

Every number that ends up in an elimination entry is computed by
deterministic, unit-tested Python (`matching/`, `eliminations/`), with a
net-zero invariant enforced as a model validator on `Elimination`. The
model's entire job is triage: given an exception, decide whether it looks
safe to auto-resolve and write the rationale a reviewer should read first.
No LLM call ever sees a number and is asked to do anything with it other
than read it as context. When `finalize` books an auto-resolved exception,
it pulls the amount from the exception's own legs, never from anything
triage returned.

## Alternatives considered

- **Let the model compute amounts and verify them in code.** Verification
  would need the deterministic computation anyway, at which point the model
  adds cost and variance and nothing else.
- **Let the model propose amounts as a fallback when legs are missing.**
  Rejected: an invented amount with a confident rationale is the worst
  output this system could produce.

## Consequences

The arithmetic is fully testable offline and identical on every run. The
model can be swapped, degraded or absent without any figure changing. What
the model says about a number can be wrong without any number being wrong.
