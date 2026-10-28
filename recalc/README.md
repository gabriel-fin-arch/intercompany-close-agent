# recalc/ — the independent recalculation

I recalculate the sample close here, by hand, in plain SQL. The pipeline in
`src/` is built by an AI assistant; I don't take its figures on trust. The
same inputs, the same rules, written again from scratch in DuckDB — if the
two disagree, something gets investigated, not averaged.

## Authorship

Everything in this directory is written by me, Gabriel. An LLM may explain
SQL syntax to me in a separate chat, with examples that are not these data,
and it may review my pull requests in GitHub comments; it does not write
lines in these files. My commits here carry no `Co-Authored-By` line because
none applies. If that ever changes, the commit says so.

## What `ic_recalc.sql` checks

1. **Tie-out per entity** (`recalc_tieout`): the intercompany subledger
   against the control accounts `1000-IC-REC` + `2000-IC-PAY` in the trial
   balance. A variance over 1.00 is a break. On the sample data exactly
   one entity breaks: `US01`, variance −2,536.01.
2. **Matching** (`recalc_pairs`): legs grouped by `reference`, one outcome
   each — `clean`, or the first exception rule that fires, in this order:
   `self_dealing`, `missing_counterparty`, `duplicate_reference`,
   `counterparty_mismatch`, `currency_mismatch`, `sign_mismatch`,
   `amount_mismatch`, `timing_gap`. On the sample data: 11 clean pairs,
   18 exceptions of 8 types. This is the minimum level agreed in #54; the
   per-type output is already there because I need the rules to decide
   "clean", the extension later is reconciliation in CI, not more SQL.
3. **Eliminated amount** (`recalc_eliminated`): for each clean pair the
   receivable leg (the positive one); the total on the sample data is
   1,465,943.91.

## How to run

From the repo root, with the DuckDB CLI installed:

```bash
duckdb -c ".read recalc/ic_recalc.sql" -c "SELECT * FROM recalc_tieout"
```

Other views to look at: `recalc_pairs`, `recalc_eliminated`.

## Cross-check against the pipeline

`uv run python -m intercompany_close_agent.cli demo` reports, from its own
code path: the same tie-out break (`US01`, −2,536.01), the same 11 clean
pairs, the same 18 exceptions, and a 16-item reviewer worklist — the two
exceptions not on the worklist are the two `amount_mismatch` pairs under
materiality, which the triage proposes for auto-elimination. I compared
exception by exception on 28 Oct 2026 and found no difference.
