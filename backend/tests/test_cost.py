from dataclasses import dataclass

from backend.cost import compute_cost, cost_event
from backend.llm import SONNET


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


def test_compute_cost_basic_math():
    usage = FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    breakdown = compute_cost(SONNET, usage)
    assert breakdown.usd == 3.00 + 15.00


def test_compute_cost_includes_cache_write_and_read():
    usage = FakeUsage(
        input_tokens=0, output_tokens=0,
        cache_creation_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    breakdown = compute_cost(SONNET, usage)
    assert breakdown.usd == 3.75 + 0.30


def test_compute_cost_zero_usage_is_free():
    usage = FakeUsage(input_tokens=0, output_tokens=0)
    assert compute_cost(SONNET, usage).usd == 0.0


def test_cost_event_shape_matches_sse_contract():
    usage = FakeUsage(input_tokens=1000, output_tokens=200, cache_read_input_tokens=500)
    event = cost_event(compute_cost(SONNET, usage))
    assert event["event"] == "cost"
    assert set(event["data"]) == {"model", "input_tokens", "output_tokens", "cached_tokens", "usd"}
    assert event["data"]["cached_tokens"] == 500
    assert event["data"]["model"] == SONNET
