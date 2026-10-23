# ADR 0005: Whoever prepares the close cannot approve what it books

- Status: Accepted, 23 October 2026
- Decision owner: Gabriel

## Context

Segregation of duties is the oldest control in accounting: the person who
prepares a journal is not the person who approves it. A demo pipeline could
skip this — the names are typed, not authenticated — but then the demo
would be demonstrating a close with the control that matters most removed.

## Decision

The run records who prepared it (`--prepared-by`, defaulting to the login
name, documented as typed rather than authenticated), and `finalize`
refuses an `approve` or `edit` decision whose reviewer is the preparer. A
`reject` by the preparer is allowed, because rejecting books nothing: the
control guards what gets posted, not what stays open.

## Alternatives considered

- **A warning instead of a refusal.** Rejected: a warning everyone clicks
  past is not a control.
- **Real authentication.** Out of scope for a local demo; the docs say
  plainly that names are typed, and the control's shape is what the
  portfolio is showing.

## Consequences

The rule is enforced where the booking happens, not in the UI, so no front
end can bypass it. The preparer/approver separation tests are among the
ones read line by line in review, because they encode an accounting
control, not a code detail.
