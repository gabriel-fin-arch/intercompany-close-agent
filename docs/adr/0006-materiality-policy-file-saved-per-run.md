# ADR 0006: Materiality and tolerances live in a policy file saved with every run

- Status: Accepted, 23 October 2026
- Decision owner: proposed by Claude Code, accepted by Gabriel

## Context

Materiality is a judgment, not a constant. The thresholds in this project
(USD 5,000 operational materiality, a matching tolerance of the larger of
USD 1.00 and 0.01%) are deliberate and defensible, but they are choices —
and a number booked under one threshold can't be defended later unless the
threshold it was booked under is on record with the run.

## Decision

Materiality and tolerances are read from a policy file, and a copy of the
policy is saved with every execution, alongside its outputs. The reasoning
behind each threshold is written down in `docs/architecture.md` so a
reviewer can disagree with the values without reverse-engineering the
intent. Changing a threshold is a policy change: it shows up in a diff and
in the saved policy of the next run.

## Alternatives considered

- **Constants in code.** Rejected: a code change and a policy change would
  look the same, and a saved run would not carry the thresholds it used.
- **Per-entity thresholds.** Deliberately not now: one policy, stated
  plainly, beats a matrix nobody can hold in their head.

## Consequences

Any figure in any saved run can be re-defended against the exact policy
that produced it. The tie-out tolerance is derived from the matching floor,
so the policy stays internally coherent: a group can't call a difference
rounding noise on one balance and a control failure on the total.
