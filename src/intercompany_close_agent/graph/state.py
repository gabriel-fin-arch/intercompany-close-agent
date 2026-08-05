"""The LangGraph state that flows through the close pipeline.

Every node reads the full state and returns a partial update; LangGraph
merges that into the running state before calling the next node. There's no
custom reducer here on purpose -- each node that appends to audit_trail
reads the current list and returns the whole new list itself, which is
simpler to follow than an Annotated[..., operator.add] field for a project
this size.
"""

from __future__ import annotations

from typing import TypedDict

from intercompany_close_agent.models.elimination import Elimination
from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.models.ledger import ICTransaction, TrialBalanceLine
from intercompany_close_agent.models.review import ReviewDecision
from intercompany_close_agent.triage.models import TriageResult


class CloseState(TypedDict, total=False):
    entities: list[Entity]
    trial_balance: list[TrialBalanceLine]
    ic_transactions: list[ICTransaction]

    clean_pairs: list[tuple[ICTransaction, ICTransaction]]
    exceptions: list[ICException]

    triage_results: list[TriageResult]

    review_decisions: list[ReviewDecision]
    eliminations: list[Elimination]

    audit_trail: list[str]
