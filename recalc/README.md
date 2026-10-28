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
2. **Matching** (`recalc_pairs`): legs grouped by `reference`, one row each.
   `outcome` is `clean` or `exception` — the contract level agreed in #54,
   so CI can count on it — and `exception_type` carries the first rule
   that fired, in this order: `self_dealing`, `missing_counterparty`,
   `duplicate_reference`, `counterparty_mismatch`, `currency_mismatch`,
   `sign_mismatch`, `amount_mismatch`, `timing_gap`. On the sample data:
   11 clean pairs, 18 exceptions of 8 types. The per-type column is
   already there because I need the rules to decide "clean"; the
   extension later is reconciliation in CI, not more SQL.
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
pairs, the same 18 exceptions, and a 16-item reviewer worklist. Those four
figures are what `demo` prints, and they match.

Two claims in the list above do not come from `demo`'s output, and I don't
want to hide that:

- The two exceptions off the worklist (`ROYALTY-2025-1001` and
  `LOAN-INT-2025-1019`, nets −3,085.12 and −1,156.76) and the triage's
  auto-resolvable call on them are not printed by `demo`. I checked them
  offline against `match_transactions()` and `triage_exception()` on
  28 Oct 2026.
- The eliminated total 1,465,943.91 is not printed by `demo` either. It
  does match the pipeline — `receivable_amount()` summed over the clean
  pairs gives 1,465,943.91 — but that was a SQL-to-pipeline comparison I
  ran myself, not a figure either side prints. The "second,
  differently-shaped query" in the PR only checked the SQL against
  itself.
