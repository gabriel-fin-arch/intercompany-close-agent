# Where the human sits, and why

This is the part of the project that actually matters. Automating the
matching and the arithmetic is the easy 80%. The hard 20% -- and the part
that determines whether a tool like this is trustworthy in a real close --
is deciding what it should never be allowed to decide on its own.

## The rule

Three exception types are **never** auto-resolved, no matter how small the
dollar amount:

| Exception type | Why it's always a human call |
|---|---|
| `missing_counterparty` | Nothing is wrong with an *amount* here -- a booking simply doesn't exist. Auto-resolving this means inventing a transaction that was never recorded. That's not a matching problem, it's a "someone needs to go find out what happened" problem. |
| `counterparty_mismatch` | The balance landed against the wrong legal entity. Silently reassigning it might net the group total to the right number, but it would misstate which entity actually owes what -- which matters for local statutory filings, transfer pricing, and legal entity-level results, not just the consolidated view. |
| `duplicate_reference` | More than two legs share a reference. There's no way to know which pairing is correct without more information than the ledger data itself provides. Guessing wrong here means eliminating the wrong balance while leaving the real one standing. |

Everything else -- an amount that's off by more than tolerance, a booking
that landed outside the timing window -- *can* be auto-resolved, but only
when the residual is below the group's materiality threshold. A $12
rounding difference on a $2M intercompany loan doesn't need a human. A
$400,000 amount mismatch does, even though it's "just" an `amount_mismatch`
and not a control-flagged type.

That split is implemented identically in both triage paths --
`triage/rules.py` (the offline fallback) and the system prompt in
`triage/llm.py` (what Claude is told when it runs the live triage) -- so
the rule holds regardless of which one is doing the classifying that day.

## Why not let the model decide case by case?

Because "is this the kind of thing a model should decide" is itself not a
question the model should answer, especially under an incentive to be
helpful and unblock the pipeline. A materiality threshold and an exception
taxonomy are governance decisions -- they belong in code a human wrote and
can review in a diff, not in a prompt a model interprets fresh every run.
The LLM's job in this system starts *after* that boundary is drawn: given
"this specific exception is eligible for auto-resolution," decide whether
*this specific instance* still looks safe, and write the rationale. It
never gets to redraw the boundary itself.

This is also why the taxonomy lives in code with `# REVIEW:` comments next
to it (`matching/engine.py`, `triage/rules.py`), not buried in a prompt
somewhere. Anyone auditing this system should be able to find "what gets
auto-resolved" in one `grep`, not by reading transcripts.

## What "approve / reject / edit" actually books

A reviewer's decision on a pending exception isn't just a UI state -- each
one maps to a specific, auditable outcome in `finalize` (`graph/nodes.py`):

- **Approve** -- books an elimination using the exception's own legs (or,
  for a `missing_counterparty` case, using a human-supplied amount, since
  there's no second leg to derive one from). The narrative records who
  approved it and why.
- **Reject** -- no elimination is booked. The balance stays open at group
  level. This is a legitimate, recorded outcome, not a dead end -- it means
  "don't eliminate this without more information," and the audit trail
  reflects that explicitly rather than the item just quietly disappearing.
- **Edit** -- books an elimination at a reviewer-supplied amount instead of
  the raw residual, for cases where the correct amount is knowable but
  isn't what either system leg says (e.g. a manually confirmed true-up).

Every path leaves a trail: which exceptions were auto-resolved and by what
rule or model call, which were escalated, what a human decided and when.
`ReviewDecision.decided_at` and the running `audit_trail` list exist so
that "why does this number look the way it does" always has an answer.

## What this project deliberately doesn't try to solve

- **It doesn't try to make the auto-resolve boundary "smarter" with more
  LLM judgment.** The boundary is deliberately conservative and
  rule-based. A more permissive version would auto-resolve more, faster --
  and would be a worse tool for a real close, where the cost of a wrong
  auto-elimination is a lot higher than the cost of one more human review.
- **It doesn't try to auto-resolve `duplicate_reference` by "picking the
  best pair."** A fuzzy-matching heuristic could probably guess right most
  of the time. Most of the time isn't the bar for an elimination entry.
- **It doesn't second-guess a human decision.** Once a reviewer approves,
  rejects, or edits, that's what gets booked -- there's no confidence
  threshold at which the system overrides a person.

If this project grows past a portfolio piece, the honest next step isn't a
smarter model -- it's making the escalation and audit trail integrate with
whatever the group already uses for SOX evidence, so "who approved what"
lives in the system of record, not just in this repo's state.
