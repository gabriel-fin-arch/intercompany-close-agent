"""Picks the LLM-backed or offline rule-based triage implementation.

This is the one place in the codebase that decides which triage path runs.
Whichever one it picks, the caller gets back the same TriageResult shape --
the graph node, the CLI and the dashboard never need to know which one
actually produced it.
"""

from __future__ import annotations

import os

from intercompany_close_agent.models.exception import ICException
from intercompany_close_agent.triage.models import TriageResult


def _llm_is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(os.environ.get("ANTHROPIC_MODEL"))


def triage_exception(exc: ICException) -> TriageResult:
    if _llm_is_configured():
        from intercompany_close_agent.triage.llm import triage_exception as llm_triage

        try:
            return llm_triage(exc)
        except Exception:
            # A live model call can fail for all sorts of reasons -- rate
            # limit, network blip, an unexpected response shape. Falling
            # back to the deterministic rules keeps the close moving
            # instead of taking the whole run down over one exception.
            from intercompany_close_agent.triage.rules import triage_exception as rules_triage

            return rules_triage(exc)

    from intercompany_close_agent.triage.rules import triage_exception as rules_triage

    return rules_triage(exc)


def triage_all(exceptions: list[ICException]) -> list[TriageResult]:
    return [triage_exception(exc) for exc in exceptions]
