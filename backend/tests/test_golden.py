"""Runs golden/cases.yaml as a pytest -- one test per case, so a failure
names the specific case instead of a single opaque pass/fail. Skipped
without ANTHROPIC_API_KEY, same as test_graph_live.py: this replays real
utterances through the real model, it is an eval, not a unit test.
"""

import asyncio
import os
import sys
from pathlib import Path

import anthropic
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.catalog import Catalog  # noqa: E402
from backend.llm import LLMClient  # noqa: E402
from backend.providers import MockProvider  # noqa: E402
from golden.run_golden import CaseFailure, load_cases, run_case  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires a real ANTHROPIC_API_KEY (golden cases are an eval, not a unit test)",
)

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_case(case):
    async def run():
        async with httpx.AsyncClient() as http_client:
            catalog = await Catalog.load(http_client)
            provider = MockProvider(catalog)
            llm = LLMClient(anthropic.AsyncAnthropic())
            return await run_case(case, catalog, provider, llm)

    try:
        notes = asyncio.run(run())
    except CaseFailure as exc:
        pytest.fail(str(exc))
    else:
        print(f"{case['name']}: " + "; ".join(notes))
