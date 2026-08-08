"""FastAPI endpoint tests. TestClient is used WITHOUT the `with` context
manager, which deliberately skips the ASGI lifespan (verified empirically
before writing this file) -- so the real Catalog.load()/Anthropic client
in main.py's lifespan never runs. app.state is populated with fakes
directly instead.
"""

from fastapi.testclient import TestClient

from backend.catalog import Catalog, Player, Team
from backend.harness import SessionStore
from backend.main import app
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


def wire_fake_state(llm):
    catalog = make_catalog()
    app.state.catalog = catalog
    app.state.llm = llm
    app.state.provider = MockProvider(catalog)
    app.state.mock_provider = MockProvider(catalog)
    app.state.sessions = SessionStore()


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_endpoint_streams_sse_events():
    wire_fake_state(FakeLLMClient([
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Knicks"})),
        text_msg("Teams are set."),
    ]))
    client = TestClient(app)

    with client.stream("POST", "/api/chat", json={"session_id": "s1", "message": "Celtics and Knicks"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())

    assert "event: tool_call" in body
    assert "event: state_diff" in body
    assert "event: assistant" in body
    assert body.rstrip().endswith("event: done\ndata: {}")


def test_chat_endpoint_persists_session_across_two_requests():
    wire_fake_state(FakeLLMClient([
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Knicks"})),
        text_msg("Teams are set."),
        tool_call_msg(("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"})),
        text_msg("Queta added."),
    ]))
    client = TestClient(app)

    with client.stream("POST", "/api/chat", json={"session_id": "s2", "message": "Celtics and Knicks"}):
        pass
    with client.stream("POST", "/api/chat", json={"session_id": "s2", "message": "add Queta"}):
        pass

    session = app.state.sessions.get_or_create("s2")
    assert session.trade.team_ids == [2, 20]
    assert len(session.trade.assets) == 1
    # second call's interpret should have seen the first turn's history
    second_call_messages = app.state.llm.calls[2]["messages"]
    assert len(second_call_messages) > 2
