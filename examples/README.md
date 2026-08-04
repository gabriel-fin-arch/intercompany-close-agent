# Examples

**`sample_cli_run.txt`** -- real output from:

```
uv run python -m intercompany_close_agent.cli run
```

against the committed `data/synthetic/` dataset, offline (no
`ANTHROPIC_API_KEY` set). Shows the audit trail and the full reviewer
worklist, including a `counterparty_mismatch`, a `timing_gap`, several
`missing_counterparty` cases, and an `amount_mismatch` -- one real example
of each exception type the matching engine detects.

Several entries also carry a note that one of the entities involved keys
its data in by hand -- that's `ZA01`, the group's non-interfaced entity,
and triage surfaces it because a manually loaded balance is a weaker
starting point than one that arrived through a system interface.

Note that a few `missing_counterparty` pairs show up twice, from both
sides (e.g. `LOAN-INT-2025-1010` and `LOAN_INT-2025-1010`) -- that's the
`non_interfaced_noise` anomaly from the synthetic data generator doing
exactly what it's meant to: a manually re-keyed reference (dropped hyphen)
makes what should be one balance look like two separate missing-counterparty
exceptions. The matching engine doesn't fuzzy-match references back
together on purpose -- see `docs/human-in-the-loop.md` for why.

## Dashboard

Not included as a static image here -- run it yourself, it's more honest
than a screenshot:

```
uv run streamlit run app/streamlit_app.py
```

Click **Run close pipeline** against the default data directory, and the
same worklist from `sample_cli_run.txt` renders as an interactive review
screen with approve/reject/edit per item.
