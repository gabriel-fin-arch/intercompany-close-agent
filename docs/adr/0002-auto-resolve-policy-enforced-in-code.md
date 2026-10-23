# ADR 0002: The auto-resolve policy is enforced in code, after any classifier

- Status: Accepted, 23 October 2026
- Decision owner: proposed by Claude Code, accepted by Gabriel

## Context

Auto-resolution is gated by three rules: the exception type is not one of
the six that always need judgment, the amount at stake is below
materiality, and no entity on either side loads manually. Stating those
rules in the triage prompt is necessary but not sufficient, because part of
what goes into that prompt isn't ours: an intercompany reference is free
text typed by whoever submitted the balance, and it lands inside the prompt
verbatim. A reference carrying an instruction — or a live model simply
being wrong about materiality — could return `auto_resolvable` for
something that must never be.

## Decision

The whole policy is re-checked in code, after the classifier returns, on
either path: `_enforce_taxonomy` (`triage/node.py`) sits between any
classifier and its caller. If the result says auto-resolvable for a
judgment-only type, for an amount above materiality, or for a balance
touching a manually loaded entity, it is overridden, and the override is
written into the rationale the reviewer reads, alongside what the
classifier originally said. Nothing that arrives through a prompt can reach
this check.

## Alternatives considered

- **Policy in the system prompt only.** Rejected: a prompt is a request,
  not a guarantee. If a guarantee matters, it belongs in code the model
  can't see.
- **Schema validation of classifier output.** Necessary but insufficient:
  a schema can check shape, not whether auto-resolution is allowed for this
  exception.

## Consequences

The policy holds identically under the rules path, the model path, and a
compromised model; `tests/test_triage_node.py` pins one compromised-model
test per check. Overrides are visible to the reviewer instead of silent.
The taxonomy lives in code with a `# REVIEW:` comment, findable with one
`grep`.
