import asyncio

import pytest

from backend.catalog import Catalog, Player, Team
from backend.harness import Session, SessionStore, format_sse, handle_chat
from backend.providers import MockProvider
from backend.tests.test_graph import FakeLLMClient, text_msg, tool_call_msg

TEAMS = [
    Team(id=2, name="Celtics", abbreviation="BOS", city="Boston",
         totalSalary=201669287, capSpace=-36669287, isOverCap=True,
         isOverLuxuryTax=True, isOverFirstApron=False, isOverSecondApron=False),
    Team(id=20, name="Knicks", abbreviation="NYK", city="New York",
         totalSalary=217563917, capSpace=-52563917, isOverCap=True,
         isOverLuxuryTax=True, isOverFirstApron=True, isOverSecondApron=False),
]
PLAYERS = [
    Player(id=16998, name="Neemias Queta", teamId=2, teamName="Celtics",
           salary=2667944, noTradeClause=False, signingStatus="active"),
]


def make_catalog() -> Catalog:
    return Catalog(TEAMS, PLAYERS, [])


def test_session_store_returns_same_session_for_same_id():
    store = SessionStore()
    a1 = store.get_or_create("abc")
    a2 = store.get_or_create("abc")
    b = store.get_or_create("xyz")
    assert a1 is a2
    assert a1 is not b


def test_session_store_evicts_oldest_session_once_at_capacity():
    # session_id is unauthenticated and client-supplied -- an unbounded
    # store is a memory-exhaustion DoS vector. Capacity + oldest-first
    # eviction keeps a single process bounded.
    store = SessionStore(max_sessions=2)
    first = store.get_or_create("s1")
    store.get_or_create("s2")
    store.get_or_create("s3")  # evicts s1, the least-recently-used

    assert store.get_or_create("s1") is not first
    assert len(store._sessions) == 2


def test_session_store_touching_a_session_protects_it_from_eviction():
    store = SessionStore(max_sessions=2)
    s1 = store.get_or_create("s1")
    store.get_or_create("s2")
    store.get_or_create("s1")  # touch s1 -- s2 is now the oldest
    store.get_or_create("s3")  # evicts s2, not s1

    assert store.get_or_create("s1") is s1


def test_format_sse_wire_shape():
    text = format_sse({"event": "assistant", "data": {"text": "hi"}})
    assert text == 'event: assistant\ndata: {"text": "hi"}\n\n'


def test_format_sse_validates_via_schema():
    with pytest.raises(Exception):
        format_sse({"event": "not_a_real_event", "data": {}})


async def _collect(gen):
    return [chunk async for chunk in gen]


def test_handle_chat_streams_sse_and_persists_session_messages():
    catalog = make_catalog()
    llm = FakeLLMClient([
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Knicks"})),
        text_msg("Teams are set."),
    ])
    session = Session()

    chunks = asyncio.run(_collect(handle_chat(
        session=session, user_text="Celtics and Knicks", catalog=catalog,
        provider=MockProvider(catalog), llm=llm, mock_provider=MockProvider(catalog),
    )))

    assert all(c.startswith("event: ") for c in chunks)
    assert chunks[-1] == 'event: done\ndata: {}\n\n'
    assert "event: tool_call" in chunks[0]
    assert session.trade.team_ids == [2, 20]
    assert len(session.messages) > 0  # persisted for the next turn


def test_handle_chat_emits_server_error_event_on_runaway_loop_instead_of_dying_silently():
    catalog = make_catalog()
    # Never resolves cleanly -- exhausts the default recursion_limit.
    llm = FakeLLMClient([
        tool_call_msg(("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}))
        for _ in range(50)
    ])
    session = Session()
    session.trade.team_ids = [2, 20]

    chunks = asyncio.run(_collect(handle_chat(
        session=session, user_text="add Queta", catalog=catalog,
        provider=MockProvider(catalog), llm=llm, mock_provider=MockProvider(catalog),
    )))

    assert any("event: error" in c and "server_error" in c for c in chunks)
    assert chunks[-1] == 'event: done\ndata: {}\n\n'  # stream still ends cleanly, never just hangs/dies
    # The raw exception text (e.g. "GraphRecursionError: ...") must never
    # reach the client -- only a generic message (A10: don't leak internals
    # through an exceptional-condition path).
    error_chunk = next(c for c in chunks if "server_error" in c)
    assert "GraphRecursionError" not in error_chunk
    assert "Something went wrong" in error_chunk
