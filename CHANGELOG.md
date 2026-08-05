# Changelog

All notable changes to this project are logged here.

## [Unreleased]

### Added
- Project scaffolding (uv, pyproject.toml, license, package layout).
- `Entity` model.
- `TrialBalanceLine` / `ICTransaction` models, CSV loaders with COA mapping.
- Synthetic dataset generator (7 entities, 7 anomaly types) + committed sample output.
- Deterministic IC matching engine: reference pairing, counterparty consistency,
  amount tolerance, timing-gap and duplicate-reference detection, with full test
  coverage including an integration test against the real synthetic dataset.
- Elimination JE generation from matched pairs, with a balance invariant enforced
  at the model level.
- LangGraph close pipeline: ingest -> normalize -> match -> triage -> human_review -> finalize.
  Triage runs against Claude (langchain-anthropic, model from ANTHROPIC_MODEL) or a deterministic
  rule-based fallback when no API key/model is configured -- same result shape either way, and the
  fallback also catches any live-call failure so one bad LLM response can't take the close down.
  human_review uses LangGraph's native interrupt() to pause the run for anything that needs a
  person's judgment; nothing is auto-eliminated past that point without an explicit decision.
- CLI (typer): `generate-data` and `run`. `run` works fully offline and prints the reviewer
  worklist for anything pending human review.
- Streamlit reviewer dashboard: run the pipeline, review the worklist, approve/reject/edit each
  pending item, and see the finalized eliminations and audit trail.
