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
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import AsyncIterator

from .catalog import Catalog
from .graph import stream_turn
from .llm import LLMClient
from .providers import VerdictProvider
from .schemas import SSEEvent
from .state import TradeState

logger = logging.getLogger(__name__)

# session_id is client-supplied and unauthenticated (auth is out of scope
# per human-plan.md) -- without a cap, an attacker (or just many real
# visitors) growing distinct session_ids forever is an unbounded-memory
# DoS. A hard cap + oldest-evicted-first keeps a single process bounded
# without adding a real eviction/TTL subsystem for a prototype.
MAX_SESSIONS = 1000


@dataclass
class Session:
    trade: TradeState = field(default_factory=TradeState)
    messages: list[dict] = field(default_factory=list)


class SessionStore:
    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self._sessions: "OrderedDict[str, Session]" = OrderedDict()
        self._max_sessions = max_sessions

    def get_or_create(self, session_id: str) -> Session:
        if session_id in self._sessions:
            self._sessions.move_to_end(session_id)
            return self._sessions[session_id]
        if len(self._sessions) >= self._max_sessions:
            evicted_id, _ = self._sessions.popitem(last=False)
            logger.info("session store at capacity, evicted oldest session %s", evicted_id)
        session = Session()
        self._sessions[session_id] = session
        return session


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
    except Exception:
        # Never disconnect silently -- an unexpected failure (a runaway-loop
        # GraphRecursionError, an uncaught API error) still gets a visible
        # error event before the stream ends, matching human-plan.md's
        # "illegal verdicts are never silent" bar extended to hard failures.
        # session.messages is deliberately NOT updated here, so the next
        # turn retries from the last known-good history.
        #
        # The exception's own text is logged server-side, never sent to the
        # client: str(exc) can carry internals (file paths, library repr,
        # a partial stack) that are useful for us and meaningless -- or a
        # disclosure risk -- for the user (A10: mishandling exceptional
        # conditions should not leak internals).
        logger.exception("unhandled error mid-turn")
        yield format_sse({
            "event": "error",
            "data": {"kind": "server_error", "message": "Something went wrong on our end. Please try again."},
        })
    yield format_sse({"event": "done", "data": {}})
