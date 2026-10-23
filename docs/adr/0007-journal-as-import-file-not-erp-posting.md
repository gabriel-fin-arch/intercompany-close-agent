# ADR 0007: The journal is an import file, not a posting to an ERP

- Status: Accepted, 23 October 2026
- Decision owner: Gabriel

## Context

The close's output is a set of elimination entries. There is no ERP here to
post them to, and pretending there is one — a mock endpoint, a "posted"
flag — would manufacture evidence of a step that never happened. What a
real group needs from this stage is a file its ERP can import.

## Decision

The journal is exported as files to import: the Dynamics 365 Finance
general journal format, plus a generic CSV, with a note on Lucanet (whose
public documentation has no field-level posting import format). The
assumptions are written down in `docs/journal-export.md` — the entity as a
dimension segment, the `ICElim` journal name — and the repo never says
Dynamics is the owner's ERP: it is the format chosen for the example, not a
claim about anyone's landscape. The export template ships filled with the
sample data, so whoever opens it sees the format in use, not only headers.

## Alternatives considered

- **Post to a mocked ERP API.** Rejected: it would demonstrate an
  integration that doesn't exist and produce screenshots of a fake.
- **Generic CSV only.** Rejected: one real, named format shows the work of
  mapping to an actual import contract; the CSV covers everyone else.

## Consequences

Every posted entry is verifiable against the file that would carry it into
a real system. The posting date is inferred from the close period — a
choice the tests defended by catching a September close dated 31 October,
which is exactly the kind of bug a test exists for.
