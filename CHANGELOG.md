# Changelog

All notable changes to this project are logged here.

## [Unreleased]

### Fixed
- Dependency floors that could not run the code. `typer>=0.12` crashes on
  `--help` against current click (0.16 is the first that works),
  `langgraph-checkpoint` was imported but never declared and needs 4.0.1 for
  `allowed_msgpack_modules`, and `starlette<1.4` had no floor at all, so a
  lowest-version install picked starlette 0.1.0. Checked by installing the
  lowest versions the constraints allow and running the suite.
- `generate-data` wrote CRLF, so following the README left the three committed
  CSVs showing as modified in a clean clone. Rows end in LF now, and a test
  regenerates the sample and compares it byte for byte.

## [0.1.0] - 2026-01-09

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
