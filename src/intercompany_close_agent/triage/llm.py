"""LLM-backed triage using Claude via langchain-anthropic.

The model is DEFAULT_MODEL unless ANTHROPIC_MODEL names another, read at
call time. This module only ever classifies an exception and writes a
rationale; it never touches the numbers. The deterministic matching engine
already decided the amounts. The model's job here is judgment, not
arithmetic.
"""

from __future__ import annotations

import os
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.triage.metering import CallRecord
from intercompany_close_agent.triage.models import TriageJudgment, TriageResult

# The model a run uses when ANTHROPIC_MODEL is unset, and the one the triage
# eval measures (docs/triage-eval.md). Pinned so a reader knows which model a
# run means, as revrec pins its own.
DEFAULT_MODEL = "claude-opus-5-5"

# A judgment is a classification, a confidence and a few sentences, but Opus
# 5.5 always thinks first (adaptive thinking can't be turned off on it), and
# the thinking counts as output. Without a cap, langchain-anthropic asks for
# the model's maximum, 128,000 tokens on Opus 5.5, which leaves a cost
# estimate with no useful ceiling. An answer cut off at the cap doesn't
# parse, and a close falls back to the rules for it, with a warning. The same
# cap as revrec's.
MAX_TOKENS = 16000

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


def model_name() -> str:
    return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


def _build_chain(include_raw: bool = False):
    # No temperature. Claude 4.7 and later reject any non-default value with a
    # 400, and the fallback in triage/node.py used to swallow that, so every
    # run against a current model quietly came back from the rules instead.
    # `model` and `max_tokens` are ChatAnthropic's documented keywords; the
    # fields' aliases are `model_name` and `max_tokens_to_sample`, and mypy
    # only sees the aliases.
    llm = ChatAnthropic(model=model_name(), max_tokens=MAX_TOKENS)  # type: ignore[call-arg]
    # json_schema is the API's own structured output. The default,
    # function_calling, forces a tool call, which Opus 5.5 doesn't accept:
    # langchain-anthropic then leaves the tool optional, and an answer that
    # doesn't call it fails. include_raw keeps the model's message next to the
    # parsed judgment, for the token counts the eval costs a call from.
    structured_llm = llm.with_structured_output(TriageJudgment, method="json_schema", include_raw=include_raw)
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


def _result(exc: ICException, judgment: Any) -> TriageResult:
    if not isinstance(judgment, TriageJudgment):
        judgment = TriageJudgment.model_validate(judgment)
    return TriageResult(reference=exc.reference, **judgment.model_dump())


def triage_exception(exc: ICException, entities: dict[str, Entity] | None = None) -> TriageResult:
    chain = _build_chain()
    return _result(exc, chain.invoke({"exception_details": _describe(exc, entities)}))


def triage_measured(
    exc: ICException, entities: dict[str, Entity] | None = None
) -> tuple[TriageResult, CallRecord]:
    """The same call as `triage_exception`, with what it cost and how long it took.

    For the triage eval. An answer that doesn't parse raises, as it does in a
    close; there the node falls back to the rules, here the eval records the
    case as failed, with the call's cost, rather than score the rules under
    the model's name.
    """
    chain = _build_chain(include_raw=True)
    started = time.perf_counter()
    output = chain.invoke({"exception_details": _describe(exc, entities)})
    seconds = time.perf_counter() - started
    usage = getattr(output.get("raw"), "usage_metadata", None)
    call = CallRecord.from_usage(dict(usage) if usage else None, model_name(), seconds)
    if output.get("parsing_error") is not None or output.get("parsed") is None:
        raise UnparsedAnswer(str(output.get("parsing_error") or "no structured output"), call)
    return _result(exc, output["parsed"]), call


class UnparsedAnswer(ValueError):
    """The model answered, but not in the TriageJudgment shape."""

    def __init__(self, detail: str, call: CallRecord) -> None:
        super().__init__(f"the model's answer didn't parse: {detail}")
        self.call = call
