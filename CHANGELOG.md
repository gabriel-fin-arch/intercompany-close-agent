# Changelog

All notable changes to this project are logged here.

## [Unreleased]

### Fixed
- The README's note on the commit history took up most of the first screen.
  It's shorter now and keeps every fact; the detail, including the earlier
  account, is in `PROVENANCE.md`.
- The note on the commit history, in the README and `PROVENANCE.md`, still
  said I built this in 2025 and rebuilt a lost git history when publishing.
  Neither is true: I built it in August 2026, and the commits were backdated as
  they were made. Both say so now, along with what I said earlier that wasn't
  true. The licence year is 2026, and the 0.1.0 entry below gives the date it
  was tagged.
- `langchain-anthropic` below 1.7.3 forces a tool call to get structured
  output, which Claude Opus 5.5, Sonnet 5.5 and Fable 5.1 reject with a 400, so
  live triage fell back to the rules on every exception with those models. The
  floor is 1.7.3 now.
- The README's note on the commit history left out what the publishing
  rewrites actually did. It says so now, and `PROVENANCE.md` lists every
  force-push, the re-created tag and the deleted CI runs, with how to check
  each one.
- The live triage path never ran against a current model. It set
  `temperature=0`, which Claude 4.7 and later reject with a 400, and the
  dispatcher's catch-all fallback turned every one of those into a rule-based
  result without a word. The temperature is gone, and a fallback now logs a
  warning naming the reference and the error.
- Dependency floors that could not run the code. `typer>=0.12` crashes on
  `--help` against current click (0.16 is the first that works),
  `langgraph-checkpoint` was imported but never declared and needs 4.0.1 for
  `allowed_msgpack_modules`, and `starlette<1.4` had no floor at all, so a
  lowest-version install picked starlette 0.1.0. Checked by installing the
  lowest versions the constraints allow and running the suite.
- `generate-data` wrote CRLF, so following the README left the three committed
  CSVs showing as modified in a clean clone. Rows end in LF now, and a test
  regenerates the sample and compares it byte for byte.
- An empty IC ledger ran to completion and printed "No items needed human
  review", which is what a clean month looks like. It is refused now, as is an
  entity code that `entities.csv` doesn't know (triage would otherwise treat it
  as interfaced). Missing files, missing columns and unparseable rows name the
  file and line instead of surfacing as a traceback, in the CLI and the
  dashboard alike.
- `Entity.interfaced` still described the confidence penalty that the
  never-auto-eliminate policy replaced.
- A timing gap was described as "Residual is material" next to a net amount of
  0.00. Its legs agree; what was banded HIGH is the balance straddling the
  cutoff, and the rationale now says that. The LLM triage prompt also listed
  only four of the six never-auto-resolved types and asked for "lower
  confidence" on manually loaded entities where the policy is never to
  auto-eliminate them. The code already enforced both; the prompt and the docs
  that quote it now agree with it.
- A clean pair only has to net to within tolerance, and its elimination left the
  difference in the payable entity's control account without a word
  (`MGMT-FEE-2025-1006` keeps -0.02 in US01). `finalize` records it the way it
  already did for exceptions. The engine docstring still called the tolerance
  "sub-dollar", which stopped being true when it became relative.

## [0.1.0] - 2026-08-10

Tagged on 10 August 2026. Earlier versions of this file, and the re-created
tag, give 9 January 2026; that date was invented (see `PROVENANCE.md`).

### Added
- Project scaffolding (uv, pyproject.toml, license, package layout).
- `Entity` model.
- `TrialBalanceLine` / `ICTransaction` models, CSV loaders with COA mapping.
- Synthetic dataset generator (7 entities, 10 anomaly types) + committed sample output.
- Deterministic IC matching engine: reference pairing, counterparty consistency,
  amount tolerance, timing-gap and duplicate-reference detection, with full test
  coverage including an integration test against the real synthetic dataset.
- Elimination JE generation from matched pairs, with a balance invariant enforced
  at the model level.
- LangGraph close pipeline: ingest -> reconcile -> match -> triage -> human_review -> finalize.
  Triage runs against Claude (langchain-anthropic, model from ANTHROPIC_MODEL) or a deterministic
  rule-based fallback when no API key/model is configured -- same result shape either way, and the
  fallback also catches any live-call failure so one bad LLM response can't take the close down.
  human_review uses LangGraph's native interrupt() to pause the run for anything that needs a
  person's judgment; nothing is auto-eliminated past that point without an explicit decision.
- CLI (typer): `generate-data` and `run`. `run` works fully offline and prints the reviewer
  worklist for anything pending human review.
- Streamlit reviewer dashboard: run the pipeline, review the worklist, approve/reject/edit each
  pending item, and see the finalized eliminations and audit trail.
- Full documentation: README (business problem, domain rationale, architecture, human-in-the-loop),
  docs/architecture.md, docs/human-in-the-loop.md, docs/data-model.md, and a real captured example run.
