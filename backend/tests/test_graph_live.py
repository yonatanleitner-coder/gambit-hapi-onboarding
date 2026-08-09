"""Optional live integration test: real Anthropic API + real bball-GM API.

Skipped by default (no network cost, no API key needed) -- runs only when
ANTHROPIC_API_KEY is set. First run: 2026-08-08, confirmed the full
interpret -> execute_tools -> validate -> respond round trip actually
works against the real APIs (see docs/end-of-session.md task 5 notes).
Re-run this after any change to graph.py/llm.py/tools.py's message
handling to catch API-shape regressions the fake-client tests can't see.
"""

import asyncio
import os

import anthropic
import httpx
import pytest

from backend.catalog import Catalog
from backend.graph import run_turn
from backend.llm import LLMClient
from backend.providers import BballGmProvider, MockProvider
from backend.state import Phase, TradeState

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires a real ANTHROPIC_API_KEY",
)


def test_live_happy_path_reaches_a_real_verdict():
    async def run():
        async with httpx.AsyncClient() as http_client:
            catalog = await Catalog.load(http_client)
            llm = LLMClient(anthropic.AsyncAnthropic())
            provider = BballGmProvider(http_client)
            mock = MockProvider(catalog)

            return await run_turn(
                trade=TradeState(),
                catalog=catalog,
                provider=provider,
                mock_provider=mock,
                llm=llm,
                messages=[{
                    "role": "user",
                    "content": (
                        "Set up a trade between the Boston Celtics and the New "
                        "York Knicks: Boston sends Neemias Queta to New York for "
                        "Andre Drummond. Then get me a verdict."
                    ),
                }],
            )

    result = asyncio.run(run())

    assert result["trade"].phase() == Phase.HAS_ASSETS
    assert set(result["trade"].team_ids) == {2, 20}
    assert {a.asset_id for a in result["trade"].assets} == {16998, 17338}
    assert result["verdict"] is not None
    assert result["verdict"].source == "api"
    assert result["hard_error"] is None

    final_text = "".join(
        block.text
        for m in result["messages"] if m["role"] == "assistant"
        for block in m["content"] if getattr(block, "type", None) == "text"
    )
    assert final_text  # respond produced real prose, not empty
    assert "{" not in final_text  # never shows raw JSON to the user
