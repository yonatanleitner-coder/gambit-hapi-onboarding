"""Golden cases: the measurable-behavior reference (ai-plan.md §9, §12
task 9). Replays fixed utterances through the REAL graph (real Anthropic
calls for interpret/respond); MockProvider stands in for CBA validation
math -- deterministic, no network, no cost on that half.

Requires ANTHROPIC_API_KEY; skipped without one (same precedent as
backend/tests/test_graph_live.py -- this is an eval of real model
behavior, not a network-free unit test, so it can't run without a key).

Run standalone: python golden/run_golden.py  (from the repo root)
Run as a test:  pytest backend/tests/test_golden.py
"""

import asyncio
import os
import sys
from pathlib import Path

import anthropic
import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.catalog import Catalog  # noqa: E402
from backend.graph import run_turn  # noqa: E402
from backend.llm import LLMClient  # noqa: E402
from backend.providers import MockProvider, VerdictProvider  # noqa: E402
from backend.state import TradeState  # noqa: E402

CASES_PATH = Path(__file__).parent / "cases.yaml"


class CaseFailure(AssertionError):
    pass


def is_subsequence(expected: list[str], actual: list[str]) -> bool:
    """True if `expected` appears in `actual` in order (not necessarily
    contiguous) -- tolerant of a real model batching or interleaving
    calls slightly differently across runs, while still requiring the
    right tools to fire in the right relative order."""
    pos = 0
    for name in expected:
        while pos < len(actual) and actual[pos] != name:
            pos += 1
        if pos == len(actual):
            return False
        pos += 1
    return True


def load_cases() -> list[dict]:
    return yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]


async def run_case(case: dict, catalog: Catalog, provider: VerdictProvider, llm: LLMClient) -> list[str]:
    """Runs one case's turns in order against a fresh TradeState, checks
    every key present in `expect`, and returns human-readable pass notes.
    Raises CaseFailure on the first unmet expectation."""
    trade = TradeState()
    messages: list[dict] = []
    all_tool_calls: list[str] = []
    result: dict = {}

    for turn in case["turns"]:
        messages.append({"role": "user", "content": turn})
        result = await run_turn(trade=trade, catalog=catalog, provider=provider, llm=llm, messages=messages)
        messages = result["messages"]
        all_tool_calls.extend(e["data"]["name"] for e in result["events"] if e["event"] == "tool_call")

    expect = case["expect"]
    notes = []

    if "tools_used" in expect:
        if not is_subsequence(expect["tools_used"], all_tool_calls):
            raise CaseFailure(f"expected tool subsequence {expect['tools_used']} not found in {all_tool_calls}")
        notes.append(f"tools_used OK: {all_tool_calls}")

    if "verdict" in expect:
        verdict = result.get("verdict")
        if verdict is None:
            raise CaseFailure(f"expected a verdict but none was reached (hard_error={result.get('hard_error')})")
        want_legal = expect["verdict"] == "legal"
        if verdict.isValid != want_legal:
            raise CaseFailure(f"expected verdict.isValid={want_legal}, got {verdict.isValid}: {verdict.summary}")
        notes.append(f"verdict OK: isValid={verdict.isValid}")

    if expect.get("resolution_error"):
        kinds = [e["data"]["kind"] for e in result["events"] if e["event"] == "error"]
        if "resolution" not in kinds:
            raise CaseFailure(f"expected a resolution error event, got error kinds: {kinds}")
        notes.append("resolution_error OK")

    if "final_assets" in expect:
        actual_names = sorted(a.name for a in trade.assets)
        expected_names = sorted(expect["final_assets"])
        if actual_names != expected_names:
            raise CaseFailure(f"expected final assets {expected_names}, got {actual_names}")
        notes.append(f"final_assets OK: {actual_names}")

    return notes


async def run_all(cases: list[dict]) -> tuple[int, int]:
    """Returns (passed, total). Prints a PASS/FAIL line per case."""
    async with httpx.AsyncClient() as http_client:
        catalog = await Catalog.load(http_client)
        provider = MockProvider(catalog)
        llm = LLMClient(anthropic.AsyncAnthropic())

        passed = 0
        for case in cases:
            name = case["name"]
            try:
                notes = await run_case(case, catalog, provider, llm)
                passed += 1
                print(f"PASS  {name}")
                for note in notes:
                    print(f"        {note}")
            except CaseFailure as exc:
                print(f"FAIL  {name}: {exc}")
        return passed, len(cases)


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set -- golden cases need a real model. Skipping (exit 0).")
        return 0

    passed, total = await run_all(load_cases())
    print(f"\n{passed}/{total} golden cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
