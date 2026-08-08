"""Thin seam around the Anthropic SDK (ai-plan.md §7).

Single-model v1: MODEL_POLICY routes every task to Sonnet. Swapping a task
to a different model later is a one-line change here, not a new
subsystem. Prompt caching (cache_control on the static system+tools
prefix) and usage/cost capture land in task 6 (cost.py) -- this is just
enough for graph.py's interpret/respond nodes to make tool-calling
requests.

NOT YET LIVE-TESTED: this session had no ANTHROPIC_API_KEY available.
graph.py and this module are exercised in tests via a fake client
(backend/tests/test_graph.py); the first thing to verify once a key is
available is a real interpret -> execute_tools -> respond round trip.
"""

from typing import Any

import anthropic

SONNET = "claude-sonnet-5"

MODEL_POLICY: dict[str, str] = {
    "interpret": SONNET,
    "respond": SONNET,
}

MAX_TOKENS = 1024


class LLMClient:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        self._client = client or anthropic.AsyncAnthropic()

    async def create(
        self,
        task: str,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> anthropic.types.Message:
        kwargs: dict[str, Any] = {
            "model": MODEL_POLICY[task],
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return await self._client.messages.create(**kwargs)
