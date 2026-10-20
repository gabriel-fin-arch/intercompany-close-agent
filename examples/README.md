# Examples

**`sample_cli_run.txt`** -- real output from:

```
uv run python -m intercompany_close_agent.cli run
```

against the committed `data/synthetic/` dataset, offline (no
`ANTHROPIC_API_KEY` set). Shows the audit trail and the full reviewer
worklist covering all eight exception types the matching engine detects:
`counterparty_mismatch`, `sign_mismatch`, `self_dealing`,
`missing_counterparty`, `duplicate_reference`, `currency_mismatch`,
`timing_gap`, and two `amount_mismatch` exceptions that are auto-resolved
below materiality rather than escalated (see the finalized elimination
count and the residual notes in `docs/architecture.md`, not the worklist
below -- neither one reaches human review). The dataset is
generated with seed `14` specifically because it's one of the few seeds
(out of the first 50 tried) that happens to exercise every type in a
single run; see `src/intercompany_close_agent/synthetic/generator.py`'s
`generate()` for why that seed and not the more obvious `42`.

The run opens with a control-account tie-out break: `US01`'s intercompany
subledger is -48894.96 against -46358.95 on its trial balance. That's planted.
`build_trial_balance_rows()` in the generator adds a posting to one entity's GL
that never reached its subledger, which is the everyday reason a control
account won't tie at close, and the tie-out step reports it before anything is
matched. Which entity it lands on depends on the seed.

Several entries also carry a note that one of the entities involved keys
its data in by hand -- that's `ZA01`, the group's non-interfaced entity,
and triage surfaces it because a manually loaded balance is a weaker
starting point than one that arrived through a system interface.

Note that a few `missing_counterparty` pairs show up twice, from both
sides (e.g. `LOAN-INT-2025-1020` and `LOAN_INT-2025-1020`, both involving
`ZA01`) -- that's the `non_interfaced_noise` anomaly from the synthetic data
generator doing exactly what it's meant to: `ZA01`, the group's one
hand-keyed entity, re-typed the reference and dropped a hyphen, so what
should be one balance looks like two separate missing-counterparty
exceptions. That noise only ever attaches to a balance `ZA01` is on --
interfaced entities load straight from the ERP and don't re-key anything.
The matching engine doesn't fuzzy-match references back together on purpose
-- see `docs/human-in-the-loop.md` for why.

## Dashboard

A screenshot is in the README (`docs/img/dashboard.png`); run it yourself
for the interactive version:

```
uv run streamlit run app/streamlit_app.py
```

Click **Run close pipeline** against the default data directory, and the
same worklist from `sample_cli_run.txt` renders as an interactive review
screen with approve/reject/edit per item.
