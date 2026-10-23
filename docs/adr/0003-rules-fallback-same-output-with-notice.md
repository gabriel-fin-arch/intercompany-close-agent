# ADR 0003: Deterministic rules as the fallback, same output shape, with a notice

- Status: Accepted, 23 October 2026
- Decision owner: proposed by Claude Code, accepted by Gabriel

## Context

The live model path needs an API key, network access and budget. CI has
none of those, and neither does a fresh clone. A triage stage that only
works with a model would make the whole pipeline untestable offline and
fragile in production: a rate limit mid-run would take the close down with
it.

## Decision

`triage/rules.py` implements the same contract as the model path — given an
`ICException`, return a `TriageResult` (`classification`, `confidence`,
`rationale`) — and runs whenever no model is configured or a model call
fails. Both paths pass through the same policy enforcement (ADR 0002).
When the rules path is used, the output says so: the rationale and the CLI
surface that a deterministic fallback produced the classification, so
nobody mistakes a regex for a model judgment.

## Alternatives considered

- **Fail hard when the model is unavailable.** Rejected: a flaky network
  would turn into a failed close, and CI would need secrets.
- **A reduced output shape for the fallback.** Rejected: every downstream
  consumer would need two code paths, and the reviewer's worklist would
  change shape depending on which classifier ran that day.

## Consequences

A fresh clone runs end to end with no key; the offline demo and the CI
pipeline exercise the same code a production network blip would hit. The
fallback is honest about what it is, and the eval-style comparison between
paths stays possible because both emit the same shape.
