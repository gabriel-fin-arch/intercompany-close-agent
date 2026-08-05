"""Wires the close pipeline into a LangGraph StateGraph.

ingest -> reconcile -> match -> triage -> human_review -> finalize

human_review is the one node that can pause the whole run: if triage found
anything that needs a human's judgment, it calls LangGraph's native
interrupt() and the graph stops there until someone resumes it with
decisions. Nothing after that point runs until they do.

Uses an in-memory checkpointer -- fine for a single CLI run or a single
Streamlit session, where the pause and the resume happen in the same
process. A production version spanning multiple processes or a restart in
between would swap MemorySaver for a persistent checkpointer (LangGraph
ships a SQLite one); nothing else about the graph would need to change.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from intercompany_close_agent.graph.nodes import finalize, human_review, ingest, match, reconcile, triage
from intercompany_close_agent.graph.state import CloseState
from intercompany_close_agent.models.control import TrialBalanceVariance
from intercompany_close_agent.models.elimination import Elimination, JournalLine, JournalLineType
from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction, TrialBalanceLine
from intercompany_close_agent.models.review import ReviewAction, ReviewDecision
from intercompany_close_agent.triage.models import TriageClassification, TriageResult

# Every type that can end up inside a checkpoint. Pausing at human_review
# serialises the whole state; resuming reads it back. LangGraph will refuse
# to deserialise types it wasn't told about in a future release, so they're
# declared here rather than left to a deprecation warning that only shows up
# on the resume path -- the one path a reviewer actually depends on.
_CHECKPOINTED_TYPES = (
    Entity,
    TrialBalanceLine,
    ICTransaction,
    TrialBalanceVariance,
    ICException,
    ExceptionType,
    Materiality,
    TriageResult,
    TriageClassification,
    ReviewDecision,
    ReviewAction,
    Elimination,
    JournalLine,
    JournalLineType,
)


def build_graph():
    graph = StateGraph(CloseState)
    graph.add_node("ingest", ingest)
    graph.add_node("reconcile", reconcile)
    graph.add_node("match", match)
    graph.add_node("triage", triage)
    graph.add_node("human_review", human_review)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "reconcile")
    graph.add_edge("reconcile", "match")
    graph.add_edge("match", "triage")
    graph.add_edge("triage", "human_review")
    graph.add_edge("human_review", "finalize")
    graph.add_edge("finalize", END)

    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINTED_TYPES)
    return graph.compile(checkpointer=MemorySaver(serde=serde))


def run_close(
    ic_transactions: list[ICTransaction],
    trial_balance: list[TrialBalanceLine],
    entities: list[Entity],
    thread_id: str = "close-run",
):
    """Start a close run. Returns (compiled_graph, config, result).

    If result contains "__interrupt__", the run paused at human_review --
    inspect result["__interrupt__"][0].value["pending_review"] for the
    worklist, collect decisions, and call resume_close(...) with the same
    compiled_graph and config to continue.
    """
    compiled = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: CloseState = {
        "entities": entities,
        "trial_balance": trial_balance,
        "ic_transactions": ic_transactions,
        "audit_trail": [],
    }
    result = compiled.invoke(initial_state, config=config)
    return compiled, config, result


def resume_close(compiled, config, decisions: list[dict]):
    """Resume a paused run with a decision dict per pending reference.

    Each decision dict should match ReviewDecision's fields, e.g.
    {"reference": "...", "action": "approve", "reviewer_note": "..."}.
    """
    return compiled.invoke(Command(resume=decisions), config=config)
