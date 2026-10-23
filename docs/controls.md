# Controls

What each control in the close is for, where the code enforces it, which
test proves it, and what a finalized run's evidence pack keeps for it. The
pack is one folder per run, written by `evidence.py`; its files are listed
at the top of that module. Alongside the CSVs it writes `close.xlsx`, the
same pack as one workbook for a reviewer who works in Excel — same columns
and values, read from the pack's own files, with a first sheet for what
`run.json` says; the CSVs stay the files to import, the workbook is for
reading.

This is a portfolio project on synthetic data. The matrix says what the code
does and how to check it, not that anyone has audited it.

Code paths are relative to `src/intercompany_close_agent/` unless they start
with `app/` or `tests/`. `tests/test_controls_doc.py` checks that every file,
function and test named here exists, that every row names a test, and that
every evidence file is one the pack writes.

| # | Control objective | Enforced in | Proved by | Evidence |
|---|---|---|---|---|
| 1 | The IC subledger agrees with each entity's trial balance before anything is eliminated; a difference is reported, not absorbed. | `reconciliation/tieout.py::reconcile_to_trial_balance`, `graph/nodes.py::reconcile` | `tests/test_tieout.py::test_variance_is_flagged_when_the_gl_has_a_posting_the_subledger_lacks`, `tests/test_tieout.py::test_against_the_real_synthetic_dataset` | `tieout.csv`, `audit_trail.txt` |
| 2 | Every IC balance is matched to its counterparty's leg, and anything that doesn't pair within tolerance is an exception. | `matching/engine.py::match_transactions` | `tests/test_matching.py::test_against_the_real_synthetic_dataset`, `tests/test_matching.py::test_fx_drift_still_fails_despite_the_relative_tolerance` | `exceptions.csv` |
| 3 | Six exception types never auto-resolve, whatever the amount and whatever a model says. | `triage/rules.py::ALWAYS_NEEDS_JUDGMENT`, `triage/node.py::_enforce_taxonomy` | `tests/test_triage_rules.py::test_counterparty_mismatch_always_needs_judgment_even_if_low_materiality`, `tests/test_triage_node.py::test_a_compromised_model_cannot_auto_resolve_an_always_escalate_type` | `exceptions.csv` (classification and rationale) |
| 4 | A material balance, or one touching a manually loaded entity, goes to a person. | `triage/rules.py::triage_exception`, `triage/node.py::_enforce_taxonomy` | `tests/test_triage_node.py::test_a_compromised_model_cannot_auto_resolve_a_material_residual`, `tests/test_triage_node.py::test_a_compromised_model_cannot_auto_resolve_a_manually_loaded_entity` | `exceptions.csv` |
| 5 | Ledger free text can't steer triage (prompt injection). | `triage/node.py::_enforce_taxonomy`, `triage/llm.py::_flatten` | `tests/test_triage_node.py::test_a_compromised_model_cannot_auto_resolve_an_always_escalate_type`, `tests/test_triage_node.py::test_injected_newlines_cannot_fake_extra_prompt_fields`, `tests/test_triage_eval.py::test_the_taxonomy_check_alone_holds_against_a_classifier_that_auto_resolves_everything`, `tests/test_triage_eval.py::test_injected_text_reaches_the_prompt_as_one_line_or_not_at_all` | `exceptions.csv` (an override is written into the rationale) |
| 6 | Nothing that triage sends to a person is booked without an explicit decision. | `graph/nodes.py::human_review`, `graph/nodes.py::finalize`, `app/streamlit_app.py` | `tests/test_graph.py::test_rejecting_a_decision_excludes_it_from_eliminations`, `tests/test_dashboard.py::test_an_untouched_worklist_is_not_submitted` | `decisions.csv`, `exceptions.csv` (booked) |
| 7 | Whoever prepares the close doesn't approve what it books. | `graph/nodes.py::finalize`, `models/review.py::same_person`, `app/streamlit_app.py` | `tests/test_graph.py::test_the_preparer_cannot_approve_what_the_run_books`, `tests/test_dashboard.py::test_the_preparer_cannot_review_the_worklist` | `run.json` (prepared_by, reviewers), `decisions.csv` |
| 8 | Every decision says who made it and when. | `models/review.py::ReviewDecision` | `tests/test_graph.py::test_a_decision_needs_someone_to_have_made_it`, `tests/test_evidence.py::test_every_decision_is_listed_with_its_reviewer_and_time` | `decisions.csv` |
| 9 | An approval the ledger can't support books nothing: a sign mismatch, a currency mismatch without a converted amount, a missing counterparty without an amount, a non-positive override. | `graph/nodes.py::finalize` | `tests/test_graph.py::test_sign_mismatch_never_auto_resolves_and_is_never_booked_on_approval`, `tests/test_graph.py::test_currency_mismatch_approved_without_an_override_is_not_booked`, `tests/test_graph.py::test_approving_a_missing_counterparty_without_an_amount_is_not_booked`, `tests/test_graph.py::test_approving_with_a_non_positive_override_is_not_booked` | `audit_trail.txt`, `exceptions.csv` (booked) |
| 10 | Every elimination entry balances, with positive amounts. | `models/elimination.py::Elimination`, `models/elimination.py::JournalLine` | `tests/test_eliminations.py::test_elimination_model_rejects_unbalanced_lines`, `tests/test_eliminations.py::test_journal_line_rejects_a_non_positive_amount` | `eliminations.csv` |
| 11 | What an elimination leaves in a control account is reported. | `graph/nodes.py::_residual_notes`, `graph/nodes.py::_within_tolerance_notes` | `tests/test_graph.py::test_finalize_surfaces_a_control_account_residual_left_by_an_elimination`, `tests/test_graph.py::test_finalize_records_what_a_within_tolerance_clean_pair_leaves_behind` | `audit_trail.txt` |
| 12 | The thresholds that decide what a person sees are set by policy and recorded with each run. | `policy.py::ClosePolicy` | `tests/test_policy.py::test_the_example_file_spells_out_the_defaults`, `tests/test_graph.py::test_the_audit_trail_opens_with_the_preparer_and_the_policy` | `run.json` (policy), `audit_trail.txt` |
| 13 | Bad input stops the close before it runs: missing files or columns, unparseable rows, an empty ledger, an entity the master data doesn't know. | `ingest/loaders.py::load_dataset` | `tests/test_loaders.py::test_a_ledger_with_no_rows_is_not_a_clean_close`, `tests/test_loaders.py::test_an_entity_missing_from_the_master_data_is_refused`, `tests/test_loaders.py::test_a_bad_amount_names_the_file_and_the_line` | None: a run that doesn't start doesn't finalize. The CLI and the dashboard say which file and line. |
| 14 | The evidence can be tied to the inputs and the code that produced it. | `evidence.py::pack_files`, `evidence.py::code_version` | `tests/test_evidence.py::test_run_json_says_who_when_under_what_policy_from_what_code_and_inputs` | `run.json` (inputs with SHA-256, code_version) |
| 15 | The journal handed to an ERP is the entries the close booked, every voucher balanced, and nothing rejected, undecided or approved by the preparer. | `journal.py::journal_rows`, `journal.py::d365_csv` | `tests/test_journal.py::test_every_voucher_balances_and_the_journal_is_the_entries_booked`, `tests/test_journal.py::test_what_the_close_did_not_book_is_not_in_the_journal` | `journal.csv`, `journal_d365.csv` |

## What this doesn't control

- **Who someone is.** Names are typed into the CLI and the dashboard, not
  authenticated. Control 7 holds on the record the run keeps; it doesn't stop
  anyone typing a colleague's name. That takes the group's own sign-in.
- **The pack after it's written.** It isn't signed, so a file in it can be
  edited afterwards. The input hashes identify what the run read; nothing
  identifies a changed pack.
- **A pause that outlives the process.** The paused run lives in memory
  (`graph/graph.py` uses `MemorySaver`), so a review has to finish in the
  session that started the close.
