"""Tokens -> USD (ai-plan.md §6). Zero external deps: a small price table
plus a pure function turning an Anthropic Usage object into a cost event.

Prices are Anthropic's standard per-MTok rates, not the temporary
introductory rate (Claude Sonnet 5 launched at a lower intro price through
2026-08-31) -- the standard rate is the durable number this table should
carry, so cost figures don't quietly change (or go stale) once the intro
window ends.
"""

from dataclasses import dataclass

from .llm import SONNET

# $ per million tokens, standard (non-introductory) API pricing.
PRICE_PER_MTOK: dict[str, dict[str, float]] = {
    SONNET: {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,  # 1.25x input -- 5-minute ephemeral TTL (the only TTL this project uses)
        "cache_read": 0.30,  # 0.1x input
    },
}


@dataclass
class CostBreakdown:
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    usd: float


def compute_cost(model: str, usage) -> CostBreakdown:
    prices = PRICE_PER_MTOK[model]
    cache_creation = usage.cache_creation_input_tokens or 0
    cache_read = usage.cache_read_input_tokens or 0

    usd = (
        usage.input_tokens * prices["input"]
        + usage.output_tokens * prices["output"]
        + cache_creation * prices["cache_write"]
        + cache_read * prices["cache_read"]
    ) / 1_000_000

    return CostBreakdown(
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
        usd=round(usd, 6),
    )


def cost_event(breakdown: CostBreakdown) -> dict:
    """ai-plan.md §8 SSE contract: cost data: {model, input_tokens,
    output_tokens, cached_tokens, usd}."""
    return {
        "event": "cost",
        "data": {
            "model": breakdown.model,
            "input_tokens": breakdown.input_tokens,
            "output_tokens": breakdown.output_tokens,
            "cached_tokens": breakdown.cache_read_input_tokens,
            "usd": breakdown.usd,
        },
    }
