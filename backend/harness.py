"""Session management + SSE formatting (ai-plan.md §10) -- thin: it owns
per-session TradeState/message history and turns stream_turn()'s event
dicts into wire-format SSE text. The actual harness logic lives in
graph.py; this module is deliberately dumb.

In-memory only, one TradeState per session -- human-plan.md scopes
persistence beyond a single session out entirely ("in-memory session"),
so a process restart loses in-flight trades. That's an accepted v1 limit,
not an oversight.
"""

import json
from dataclasses import dataclass, field
from typing import AsyncIterator

from .catalog import Catalog
from .graph import stream_turn
from .llm import LLMClient
from .providers import VerdictProvider
from .schemas import SSEEvent
from .state import TradeState


@dataclass
class Session:
    trade: TradeState = field(default_factory=TradeState)
    messages: list[dict] = field(default_factory=list)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        return self._sessions.setdefault(session_id, Session())


def format_sse(event: dict) -> str:
    validated = SSEEvent(**event)
    return f"event: {validated.event}\ndata: {json.dumps(validated.data)}\n\n"


async def handle_chat(
    *,
    session: Session,
    user_text: str,
    catalog: Catalog,
    provider: VerdictProvider,
    llm: LLMClient,
    mock_provider: VerdictProvider | None = None,
) -> AsyncIterator[str]:
    """Streams SSE-formatted text for one turn, then persists the turn's
    full message history onto `session` once the graph reaches END.
    `session.trade` needs no explicit persistence step -- tool executors
    mutate it in place, so it's already up to date."""
    turn_messages = session.messages + [{"role": "user", "content": user_text}]
    final_state: dict = {}
    try:
        async for event in stream_turn(
            trade=session.trade,
            catalog=catalog,
            provider=provider,
            llm=llm,
            messages=turn_messages,
            mock_provider=mock_provider,
            final_state_sink=final_state,
        ):
            yield format_sse(event)
        session.messages = final_state["messages"]
    except Exception as exc:
        # Never disconnect silently -- an unexpected failure (a runaway-loop
        # GraphRecursionError, an uncaught API error) still gets a visible
        # error event before the stream ends, matching human-plan.md's
        # "illegal verdicts are never silent" bar extended to hard failures.
        # session.messages is deliberately NOT updated here, so the next
        # turn retries from the last known-good history.
        yield format_sse({"event": "error", "data": {"kind": "server_error", "message": str(exc)}})
    yield format_sse({"event": "done", "data": {}})
