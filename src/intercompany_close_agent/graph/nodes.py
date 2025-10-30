"""Node functions for the intercompany close graph.

Each node is a small function of state -> partial state update. Only one of
them talks to the outside world (triage, which may call a live Claude
model); everything else is the same deterministic code already covered by
the matching/ and eliminations/ unit tests. human_review is the one node
that can pause the whole run: if triage found anything that needs a
human's judgment, it calls LangGraph's native interrupt() and the graph
stops there until someone resumes it with decisions.
"""

from __future__ import annotations

from intercompany_close_agent.eliminations.engine import build_elimination_from_exception, build_eliminations
from intercompany_close_agent.graph.state import CloseState
from intercompany_close_agent.matching.engine import match_transactions
from intercompany_close_agent.models.review import ReviewAction, ReviewDecision
from intercompany_close_agent.triage.models import TriageClassification
from intercompany_close_agent.triage.node import triage_all


def ingest(state: CloseState) -> dict:
    # entities / ic_transactions / trial_balance are loaded by the caller
    # (CLI or dashboard) before the graph runs -- this node is where a real
    # system would hit the source files or APIs directly. It's kept as an
    # explicit step so the pipeline's shape matches a real close: ingest is
    # its own stage, even though in this project the loading already
    # happened before invoke() was called.
    n_legs = len(state.get("ic_transactions", []))
    return {"audit_trail": state.get("audit_trail", []) + [f"ingested {n_legs} IC transaction legs"]}


def normalize(state: CloseState) -> dict:
    # COA mapping already happened in the loader (ingest/loaders.py). This
    # stage exists so the graph's shape says explicitly "we normalized
    # before matching" -- a real system might do FX translation or entity
    # eliminations-scope filtering here.
    return {"audit_trail": state["audit_trail"] + ["normalized ledger data"]}


def match(state: CloseState) -> dict:
    result = match_transactions(state["ic_transactions"])
    return {
        "clean_pairs": result.clean_pairs,
        "exceptions": result.exceptions,
        "audit_trail": state["audit_trail"]
        + [f"matched {len(result.clean_pairs)} clean pairs, {len(result.exceptions)} exceptions"],
    }


def triage(state: CloseState) -> dict:
    results = triage_all(state["exceptions"])
    return {
        "triage_results": results,
        "audit_trail": state["audit_trail"] + [f"triaged {len(results)} exceptions"],
    }
