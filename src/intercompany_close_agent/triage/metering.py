"""What a triage model call cost and how long it took.

Used by the triage eval (`triage/evaluation.py`), which records one CallRecord
per exception it sends to the model. Prices are Anthropic's published
first-party rates in US dollars per million tokens, as the pricing page stated
them on PRICES_AS_OF; a model missing from the table is costed as unknown
rather than guessed.

LangChain reports usage in its own shape: `input_tokens` there already
includes the tokens read from and written to the prompt cache, with the split
in `input_token_details`. The uncached part is what is left after taking
those out.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

PRICES_AS_OF = "2026-10-18"
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens."""

    input: Decimal
    cache_write: Decimal  # five-minute cache
    cache_read: Decimal
    output: Decimal


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(Decimal("4"), Decimal("5"), Decimal("0.20"), Decimal("20")),
    "claude-opus-5": Price(Decimal("5"), Decimal("6.25"), Decimal("0.50"), Decimal("25")),
}

MILLION = Decimal(1_000_000)


class CallRecord(BaseModel):
    model: str
    input_tokens: int = 0  # uncached
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0
    seconds: float
    cost_usd: Decimal | None = None
    prices_as_of: str = PRICES_AS_OF

    @classmethod
    def from_usage(cls, usage: dict[str, Any] | None, model: str, seconds: float) -> CallRecord:
        """From LangChain's `usage_metadata`, or with no usage at all."""
        if not usage:
            return cls(model=model, seconds=round(seconds, 3))
        details = usage.get("input_token_details") or {}
        cache_read = int(details.get("cache_read") or 0)
        cache_written = int(details.get("cache_creation") or 0) + sum(
            int(details.get(key) or 0) for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")
        )
        uncached = max(int(usage.get("input_tokens") or 0) - cache_read - cache_written, 0)
        output = int(usage.get("output_tokens") or 0)
        price = PRICES.get(model)
        cost = None
        if price is not None:
            total = uncached * price.input + cache_written * price.cache_write + cache_read * price.cache_read
            cost = ((total + output * price.output) / MILLION).quantize(Decimal("0.000001"))
        return cls(
            model=model,
            input_tokens=uncached,
            cache_creation_input_tokens=cache_written,
            cache_read_input_tokens=cache_read,
            output_tokens=output,
            seconds=round(seconds, 3),
            cost_usd=cost,
        )
