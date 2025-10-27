"""Types produced by the triage step -- LLM-backed or offline fallback alike.

Kept separate from the deterministic ICException model on purpose: whether
triage ran against a live Claude model or the rule-based fallback, the rest
of the pipeline only ever sees a TriageResult and never has to know which
one produced it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TriageClassification(str, Enum):
    AUTO_RESOLVABLE = "auto_resolvable"
    NEEDS_HUMAN_JUDGMENT = "needs_human_judgment"


class TriageJudgment(BaseModel):
    """What triage decides about one exception, before it's tied back to a reference."""

    classification: TriageClassification
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class TriageResult(TriageJudgment):
    """A TriageJudgment tied back to the exception it's about."""

    reference: str
