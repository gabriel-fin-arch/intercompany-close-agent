"""Reviewer dashboard for the intercompany close agent.

Streamlit reruns this whole script on every interaction, so the compiled
graph and the pipeline's paused state live in st.session_state -- otherwise
every button click would start a brand new close run from scratch instead
of resuming the one already in flight.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import DataLoadError, load_dataset
from intercompany_close_agent.models.review import ReviewAction, parse_override_amount
from intercompany_close_agent.synthetic.generator import OUTPUT_DIR as DEFAULT_DATA_DIR

load_dotenv()

st.set_page_config(page_title="Intercompany Close Agent", layout="wide")


st.title("Intercompany Close Agent")
st.caption("Matching -> eliminations -> triage -> human review, for the intercompany leg of a group close.")

with st.sidebar:
    st.header("Run")
    data_dir_input = st.text_input("Synthetic data directory", value=str(DEFAULT_DATA_DIR))
    run_clicked = st.button("Run close pipeline", type="primary")
    if st.session_state.get("result") is not None and st.button("Reset"):
        for key in ("graph", "config", "result", "final"):
            st.session_state.pop(key, None)
        st.rerun()

if run_clicked:
    try:
        entities, trial_balance, transactions = load_dataset(Path(data_dir_input))
    except DataLoadError as exc:
        st.error(f"Cannot run the close: {exc}")
        st.stop()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="dashboard-run")
    st.session_state["graph"] = graph
    st.session_state["config"] = config
    st.session_state["result"] = result
    st.session_state.pop("final", None)

result = st.session_state.get("result")
if result is None:
    st.info("Pick a data directory and click **Run close pipeline** to start.")
    st.stop()

final = st.session_state.get("final")
display_state = final if final is not None else result

n_clean = len(result.get("clean_pairs", []))
n_exceptions = len(result.get("exceptions", []))
n_pending = len(result["__interrupt__"][0].value["pending_review"]) if "__interrupt__" in result else 0
n_eliminations = len(display_state.get("eliminations", []))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Clean pairs", n_clean)
col2.metric("Exceptions", n_exceptions)
col3.metric("Pending review", n_pending if final is None else 0)
col4.metric("Eliminations finalized", n_eliminations)

tb_breaks = [v for v in result.get("tb_variances", []) if not v.within_tolerance]
if tb_breaks:
    st.warning(
        f"Control account tie-out: {len(tb_breaks)} entity(ies) where the IC subledger "
        f"doesn't agree with the trial balance. These are GL-vs-subledger data breaks, "
        f"not per-balance reconciliation items."
    )
    for variance in tb_breaks:
        st.text(
            f"  {variance.entity_code}: subledger {variance.ledger_total} vs "
            f"TB {variance.trial_balance_total} (variance {variance.variance})"
        )

st.subheader("Audit trail")
for line in display_state["audit_trail"]:
    st.text(f"- {line}")


def _render_eliminations(eliminations) -> None:
    st.subheader(f"Eliminations ({len(eliminations)})")
    for elim in eliminations:
        with st.expander(f"{elim.reference}"):
            st.write(elim.narrative)
            for line in elim.lines:
                st.text(
                    f"  {line.line_type.value.upper():>6}  {line.entity_code:<6}  "
                    f"{line.amount}  ({line.account_code})"
                )


if final is not None:
    st.success("Close finalized.")
    _render_eliminations(final.get("eliminations", []))

elif "__interrupt__" in result:
    pending = result["__interrupt__"][0].value["pending_review"]
    st.subheader(f"Reviewer worklist -- {len(pending)} item(s) need a decision")

    decisions: dict[str, dict] = {}
    for item in pending:
        header = f"[{item['materiality'].upper()}] {item['reference']} -- {item['exception_type']}"
        with st.expander(header, expanded=True):
            net_amount = item["net_amount"] or "n/a -- different currencies, no FX rate to net"
            st.write(f"**Net amount:** {net_amount}")
            st.write(f"**Why:** {item['detected_reason']}")
            st.write(f"**Triage rationale** (confidence {item['confidence']:.2f}): {item['rationale']}")

            action = st.radio(
                "Decision",
                options=[a.value for a in ReviewAction],
                key=f"action_{item['reference']}",
                horizontal=True,
            )
            note = st.text_input("Reviewer note", key=f"note_{item['reference']}")
            override_amount = None
            if action == ReviewAction.EDIT.value:
                # Left blank rather than defaulted when there's no net_amount
                # (CURRENCY_MISMATCH) -- pre-filling "n/a" would just be a
                # different way of handing back an unparseable amount.
                override_amount = st.text_input(
                    "Amount to eliminate",
                    key=f"amount_{item['reference']}",
                    value=item["net_amount"] or "",
                    help="Exact decimal amount, e.g. 1234.56",
                )

            decisions[item["reference"]] = {
                "reference": item["reference"],
                "action": action,
                "reviewer_note": note,
                "override_amount": override_amount or None,
            }

    if st.button("Submit decisions", type="primary"):
        # Validate the free-text amounts before resuming: an unparseable one
        # would otherwise crash resume_close deep in pydantic, losing the
        # whole worklist. Report each bad field and let the reviewer fix it.
        payload: list[dict] = []
        errors: list[str] = []
        for ref, decision in decisions.items():
            try:
                amount = parse_override_amount(decision["override_amount"])
            except ValueError as exc:
                errors.append(f"{ref}: {exc}")
                continue
            payload.append({**decision, "override_amount": amount})

        if errors:
            for message in errors:
                st.error(message)
        else:
            final_result = resume_close(st.session_state["graph"], st.session_state["config"], payload)
            st.session_state["final"] = final_result
            st.rerun()

else:
    st.success("No exceptions needed human review -- close finalized automatically.")
    _render_eliminations(result.get("eliminations", []))
