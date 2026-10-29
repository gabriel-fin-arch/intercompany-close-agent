# Architecture decision records

The main design decisions, one short record each: context, decision,
alternatives considered, consequences. Each was drafted from a sketch by the
project's owner and names its decision owner — his, or the assistant's that
he accepted.

> **When the project was built, and when these were written.** I designed
> this project on 5 August 2026 and built it with Claude Code: the first
> commit is from that day, as are 69 of the 89 commits made in August
> ([PROVENANCE.md](../../PROVENANCE.md)). These records came afterwards.
> Claude Code drafted them on 23 October 2026 from sketches I wrote, all in
> one commit (`ef74c2d`), so the "Accepted, 23 October 2026" at the top of
> each is the day the decision was written down, not the day it was taken.
> Why the dates need a note at all:
> [REMEDIATION.md](https://github.com/gabriel-fin-arch/gabriel-fin-arch/blob/main/REMEDIATION.md).

| # | Decision | Decision owner |
|---|---|---|
| [0001](0001-deterministic-figures-model-classifies.md) | Figures are deterministic; the model only classifies and explains | Gabriel |
| [0002](0002-auto-resolve-policy-enforced-in-code.md) | The auto-resolve policy is enforced in code, after any classifier | Claude Code, accepted by Gabriel |
| [0003](0003-rules-fallback-same-output-with-notice.md) | Deterministic rules as the fallback, same output shape, with a notice | Claude Code, accepted by Gabriel |
| [0004](0004-human-review-as-langgraph-interrupt.md) | Human review as a LangGraph interrupt — nothing is finalized without a decision | Gabriel |
| [0005](0005-preparer-cannot-approve.md) | Whoever prepares the close cannot approve what it books | Gabriel |
| [0006](0006-materiality-policy-file-saved-per-run.md) | Materiality and tolerances live in a policy file saved with every run | Claude Code, accepted by Gabriel |
| [0007](0007-journal-as-import-file-not-erp-posting.md) | The journal is an import file, not a posting to an ERP | Gabriel |

A candidate that was considered and not recorded: timing gaps measured by
accounting period rather than days — a calculation detail already in the
code, not a decision needing its own record.
