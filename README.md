# intercompany-close-agent

An agent-first assistant for the intercompany leg of a multi-entity group
consolidation close: it matches counterparty bookings, proposes elimination
journal entries with a rationale, and routes anything that genuinely needs
a person's judgment to a human reviewer instead of guessing.

Built against a synthetic dataset (seven fictional entities, none real) so
it's safe to run and inspect end to end. Runs fully offline by default --
a Claude API key upgrades the triage narrative, it doesn't change what
gets booked.

```
uv sync --extra dev
uv run python -m intercompany_close_agent.cli generate-data
uv run python -m intercompany_close_agent.cli run
uv run streamlit run app/streamlit_app.py
uv run pytest
```

---

## 1. The business problem

Every month, a consolidated group has to eliminate intercompany balances
before the numbers can go out: if entity A booked a $50,000 receivable from
entity B for a management fee, and B booked the matching $50,000 payable,
the group's books need to net that back out to zero before it hits the
consolidated P&L and balance sheet. Multiply that across dozens of entities
and hundreds of intercompany transactions a month, and the actual work
becomes: pull both sides of every balance, match them up, and figure out
what to do with the ones that don't match cleanly -- a counterparty that
never booked its side, an amount that's off by more than rounding, a
balance booked against the wrong entity, a booking that landed after the
other side's cutoff.

Most of that matching is mechanical. Some of it genuinely isn't -- and
knowing which is which, without either burying a reviewer in noise or
quietly auto-resolving something that needed a second pair of eyes, is the
actual problem this project is about.

## 2. Why it needs domain knowledge

A generic "diff two CSVs and flag what doesn't match" tool gets this wrong
in ways that matter:

- **Tolerances aren't optional.** A one-cent rounding difference and a
  $50,000 sign error are not the same kind of problem, even though both are
  "the amounts don't match." Getting the tolerance band and the materiality
  threshold right is a judgment call that reflects how the group actually
  runs its close -- not a constant you can hardcode once and forget.
- **Not every entity is equally trustworthy.** An entity whose trial balance
  loads automatically from the source ERP is a different risk profile than
  one that's keyed in by hand every month. This project's one
  non-interfaced entity (`ZA01`) carries a standing chance of manual
  re-keying noise in the synthetic data for exactly this reason.
- **Some exception types are never "small enough to auto-resolve."** A
  missing counterparty booking, a balance booked against the wrong entity,
  or a reference shared by more than two legs are control questions, not
  amount questions -- the dollar value doesn't make them safe to wave
  through. See `docs/human-in-the-loop.md` for the full reasoning.
- **US GAAP / SOX context shapes what "done" means.** An elimination that
  nets to zero on paper still needs an audit trail a controls reviewer can
  follow: what was eliminated, based on what evidence, approved by whom.
  "Approve" and "reject" aren't just UI buttons here, they're distinct
  audit trail states.

## 3. Agent architecture

```
ingest -> normalize -> match -> triage -> human_review -> finalize
```

Built as a [LangGraph](https://github.com/langchain-ai/langgraph)
`StateGraph`. Two design decisions carry the whole project:

**The LLM does not do arithmetic.** Matching two IC legs, checking a
tolerance, and building a balanced elimination entry are all deterministic
Python (`matching/`, `eliminations/`) with full unit test coverage,
including a net-zero invariant enforced at the model level. The model never
sees a number it's asked to add up -- it only ever classifies an exception
(`auto_resolvable` vs. `needs_human_judgment`) and writes the rationale a
reviewer reads. If the arithmetic and the judgment call ever lived in the
same function, you'd have no way to unit test the numbers without also
depending on a live model call.

**Triage runs against Claude, or a deterministic rule-based fallback --
same output shape either way.** With `ANTHROPIC_API_KEY` and
`ANTHROPIC_MODEL` set, `triage/llm.py` calls Claude via `langchain-anthropic`
with structured output. Without them (or if the live call fails for any
reason -- rate limit, network blip), `triage/rules.py` takes over: a small,
legible set of rules keyed on exception type and materiality. Nothing about
`graph/nodes.py` or the CLI/dashboard changes based on which path ran; they
only ever see a `TriageResult`. This is also what makes the whole project
runnable and testable without an API key.

**Where the graph can stop.** `human_review` is the only node that talks to
a person. If triage found anything that needs judgment, it calls
LangGraph's native `interrupt()` and the run pauses there -- the CLI prints
the worklist and exits; the dashboard renders it and waits for decisions.
Resuming (`Command(resume=decisions)`) picks the graph back up exactly
where it stopped. See `docs/architecture.md` for the state shape and node
details.

## 4. Where I put the human in the loop -- and why

Three exception types are **never** auto-resolved, regardless of dollar
amount: a missing counterparty booking, a balance booked against the wrong
entity, and a reference shared by more than two legs. All three are control
questions -- something is wrong with *who* booked *what*, not just *how
much* -- and no rule engine or model should get to quietly decide that's
fine because the number is small. Only genuine amount and timing residuals
get auto-resolved, and only when they're below the materiality threshold.

That taxonomy is a judgment call, not a law of nature -- it's marked with
`# REVIEW:` comments in `matching/engine.py` and `triage/rules.py` so it's
easy to find and easy to disagree with. The full reasoning, including what
"approve reject edit" actually books, lives in `docs/human-in-the-loop.md`.

## Project layout

```
src/intercompany_close_agent/
  models/        pydantic domain models (Entity, ICTransaction, ICException, Elimination, ReviewDecision, ...)
  ingest/        CSV loaders + chart-of-accounts mapping
  matching/      deterministic IC matching engine            <- unit tested
  eliminations/  elimination JE generation                   <- unit tested
  triage/        LLM triage (Claude) + offline rule fallback
  graph/         LangGraph state, nodes, and the compiled graph
  synthetic/     synthetic dataset generator
  cli.py         typer CLI
app/
  streamlit_app.py   reviewer dashboard
data/synthetic/      committed sample dataset (regeneratable)
docs/                 architecture.md, human-in-the-loop.md, data-model.md
tests/
```

## Running it

```
uv sync --extra dev

# regenerate the synthetic dataset (optional -- a sample is already committed)
uv run python -m intercompany_close_agent.cli generate-data

# run the close pipeline end to end, offline
uv run python -m intercompany_close_agent.cli run

# same, but with live Claude triage narratives instead of the rule fallback
cp .env.example .env   # then fill in ANTHROPIC_API_KEY and ANTHROPIC_MODEL
uv run python -m intercompany_close_agent.cli run

# review pending exceptions interactively
uv run streamlit run app/streamlit_app.py

# run the test suite
uv run pytest
```

## What's out of scope (for now)

FX/CTA translation, AR aging reconciliation, and Special Charges are all
real parts of a consolidation close and all deliberately out of scope here
-- this project stays narrow on purpose. They're natural extensions if this
ever grows past a portfolio piece.

## License

MIT -- see `LICENSE`.
