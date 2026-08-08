"""Thin seam around the Anthropic SDK (ai-plan.md §7).

Single-model v1: MODEL_POLICY routes every task to Sonnet. Swapping a task
to a different model later is a one-line change here, not a new subsystem.

Prompt caching (ai-plan.md §6): the system prompt carries a cache_control
breakpoint. Render order is tools -> system -> messages, so a breakpoint on
the (single) system block caches the tools that precede it too -- no
separate marker needed on the tools list. tools_for_phase() varies per
phase (task 5), so each phase gets its own cache entry; within a phase
(the common case -- HAS_ASSETS dominates a real session) repeated
interpret calls hit the cache.

Live-verified end-to-end in AI Execute (task 5 continuation, 2026-08-08):
a real interpret -> execute_tools -> validate -> respond round trip against
the live Anthropic + bball-GM APIs. See docs/end-of-session.md.
"""

from typing import Any

import anthropic

SONNET = "claude-sonnet-5"

MODEL_POLICY: dict[str, str] = {
    "interpret": SONNET,
    "respond": SONNET,
}

MAX_TOKENS = 1024


def _cached_system(system: str) -> list[dict]:
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


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
            "system": _cached_system(system),
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return await self._client.messages.create(**kwargs)
