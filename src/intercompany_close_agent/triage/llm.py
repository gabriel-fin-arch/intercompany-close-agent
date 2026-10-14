"""LLM-backed triage using Claude via langchain-anthropic.

The model is read from ANTHROPIC_MODEL at call time -- nothing in this repo
ever hardcodes a specific, dated model ID. This module only ever classifies
an exception and writes a rationale; it never touches the numbers. The
deterministic matching engine already decided the amounts. The model's job
here is judgment, not arithmetic.
"""

from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.triage.models import TriageJudgment, TriageResult

SYSTEM_PROMPT = """You are a consolidation accounting assistant helping triage \
intercompany elimination exceptions during a month-end close under US GAAP.

For the exception described below, decide whether it is safe to auto-resolve \
(draft an elimination entry automatically) or whether it needs a human \
reviewer's judgment before anything gets booked or eliminated.

Only classify something as auto_resolvable when the amount at stake is \
genuinely immaterial and there is no control concern. For an amount mismatch \
the amount at stake is the residual; for a timing gap it is the whole balance, \
because one leg of it sits in a different period. A missing counterparty \
booking, a balance booked against the wrong entity, an entity booked as its \
own counterparty, two legs in different currencies, two legs booked on the \
same side (both receivable or both payable, so no one can tell which one has \
the sign backwards), or a reference shared by more than two legs always needs \
human judgment -- no exceptions, regardless of the dollar amount.

If any entity involved is flagged as manually loaded, it needs human judgment \
too: that data was keyed in by hand rather than arriving through a system \
interface, and a small break there is not safe to eliminate unreviewed.

Write a short, specific rationale a reviewer could act on without having to \
re-derive your reasoning from scratch."""


def _build_chain():
    model_name = os.environ.get("ANTHROPIC_MODEL")
    if not model_name:
        raise RuntimeError("ANTHROPIC_MODEL is not set")
    # No temperature. Claude 4.7 and later reject any non-default value with a
    # 400, and the fallback in triage/node.py used to swallow that, so every
    # run against a current model quietly came back from the rules instead.
    llm = ChatAnthropic(model=model_name)
    structured_llm = llm.with_structured_output(TriageJudgment)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{exception_details}"),
        ]
    )
    return prompt | structured_llm


def _flatten(value: str) -> str:
    """Collapse ledger free text onto one line before it goes into the prompt.

    An intercompany reference is typed by whoever submitted the balance, so
    it is not trusted input. Left alone, a reference containing newlines can
    fake extra `key=value` lines in the block below and try to pass itself
    off as instructions. Flattening doesn't make the text safe on its own --
    the binding protection is the taxonomy check in triage/node.py, which no
    prompt can talk its way past -- but it keeps the structure honest.
    """
    return " ".join(value.split())


def _describe(exc: ICException, entities: dict[str, Entity] | None = None) -> str:
    legs_desc = "; ".join(
        f"{leg.entity_code} vs {leg.counterparty_code}: {leg.amount} {leg.currency} on {leg.transaction_date}"
        for leg in exc.legs
    )
    net_amount = exc.net_amount if exc.net_amount is not None else "not applicable (legs are in different currencies)"
    description = (
        f"reference={_flatten(exc.reference)}\n"
        f"exception_type={exc.exception_type.value}\n"
        f"materiality={exc.materiality.value}\n"
        f"net_amount={net_amount}\n"
        f"detected_reason={_flatten(exc.detected_reason)}\n"
        f"legs: {_flatten(legs_desc)}"
    )

    if entities:
        manual = sorted(
            code
            for code in exc.involved_entity_codes
            if code in entities and not entities[code].interfaced
        )
        if manual:
            description = f"{description}\nmanually_loaded_entities: {', '.join(manual)}"

    return description


def triage_exception(exc: ICException, entities: dict[str, Entity] | None = None) -> TriageResult:
    chain = _build_chain()
    judgment = chain.invoke({"exception_details": _describe(exc, entities)})
    if not isinstance(judgment, TriageJudgment):
        judgment = TriageJudgment.model_validate(judgment)
    return TriageResult(reference=exc.reference, **judgment.model_dump())
