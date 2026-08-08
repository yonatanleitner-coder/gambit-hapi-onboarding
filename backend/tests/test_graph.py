"""Exercises the graph's control flow (routing, phase gates, guards)
without a real model -- FakeLLMClient plays back scripted Anthropic-shaped
responses. MockProvider is real (deterministic, no network), so validate()
is exercised for real; only interpret/respond's model calls are faked.

Not a substitute for a live smoke test against the real Anthropic API
(see llm.py's caveat) -- that's the first thing to do once
ANTHROPIC_API_KEY is available.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.errors import GraphRecursionError

from backend.catalog import Catalog, Pick, Player, Team
from backend.graph import run_turn
from backend.providers import MockProvider
from backend.state import TradeState

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
    Player(id=17338, name="Andre Drummond", teamId=20, teamName="Knicks",
           salary=3876529, noTradeClause=False, signingStatus="active"),
]
PICKS = [
    Pick(id=12062, originalTeamId=20, originalTeamName="Knicks",
         currentTeamId=2, currentTeamName="Celtics", year=2027, round=1,
         isTradable=True),
]


def make_catalog() -> Catalog:
    return Catalog(TEAMS, PLAYERS, PICKS)


@dataclass
class FakeBlock:
    type: str
    text: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "toolu_1"


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 20
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class FakeMessage:
    content: list[Any]
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeLLMClient:
    """Returns one scripted FakeMessage per call to .create(), in order."""

    def __init__(self, script: list[FakeMessage]):
        self._script = list(script)
        self.calls: list[dict] = []

    async def create(self, task, system, messages, tools=None):
        self.calls.append({"task": task, "messages": list(messages), "tools": tools})
        return self._script.pop(0)


def text_msg(text: str) -> FakeMessage:
    return FakeMessage(content=[FakeBlock(type="text", text=text)])


def tool_call_msg(*calls: tuple[str, dict]) -> FakeMessage:
    return FakeMessage(content=[
        FakeBlock(type="tool_use", name=name, input=args, id=f"toolu_{i}")
        for i, (name, args) in enumerate(calls)
    ])


def test_happy_path_reaches_verdict_and_respond():
    catalog = make_catalog()
    llm = FakeLLMClient([
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Knicks"})),
        tool_call_msg(
            ("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}),
            ("add_player", {"player": "Drummond", "from_team": "Knicks", "to_team": "Celtics"}),
        ),
        tool_call_msg(("request_verdict", {})),
        text_msg("Legal trade! Boston sends Queta, Knicks send Drummond."),
    ])
    result = asyncio.run(run_turn(
        trade=TradeState(),
        catalog=catalog,
        provider=MockProvider(catalog),  # "real" provider is mock here -- no network in this test
        llm=llm,
        messages=[{"role": "user", "content": "Boston sends Queta to New York for Drummond"}],
    ))

    assert result["trade"].team_ids == [2, 20]
    assert len(result["trade"].assets) == 2
    assert result["verdict"] is not None
    assert result["verdict"].source == "mock"
    assert any(e["event"] == "verdict" for e in result["events"])
    assert any(e["event"] == "assistant" for e in result["events"])
    # 4 LLM calls: 3 interpret turns (set_teams, 2xadd_player, request_verdict) + 1 respond
    assert len(llm.calls) == 4


def test_tool_error_loops_back_to_interpret_not_respond():
    catalog = make_catalog()
    llm = FakeLLMClient([
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Lakers"})),  # Lakers unresolvable
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Knicks"})),  # model retries correctly
        text_msg("Got it, teams are set."),
    ])
    result = asyncio.run(run_turn(
        trade=TradeState(),
        catalog=catalog,
        provider=MockProvider(catalog),
        llm=llm,
        messages=[{"role": "user", "content": "Celtics and Lakers"}],
    ))

    assert result["trade"].team_ids == [2, 20]  # first bad call never mutated state
    # first execute_tools result should carry an error tool_result
    first_tool_result_msg = result["messages"][2]
    assert first_tool_result_msg["role"] == "user"
    assert "error" in first_tool_result_msg["content"][0]["content"]


def test_hallucinated_request_verdict_before_has_assets_is_blocked():
    # Even though request_verdict isn't offered pre-HAS_ASSETS, simulate a
    # model that calls it anyway -- defense in depth (tools.py's
    # exec_request_verdict phase check) must still catch it.
    catalog = make_catalog()
    llm = FakeLLMClient([
        tool_call_msg(("set_teams", {"team_a": "Celtics", "team_b": "Knicks"})),
        tool_call_msg(("request_verdict", {})),  # hallucinated: phase is TEAMS_SET, no assets yet
        text_msg("Let's add some players first."),
    ])
    result = asyncio.run(run_turn(
        trade=TradeState(),
        catalog=catalog,
        provider=MockProvider(catalog),
        llm=llm,
        messages=[{"role": "user", "content": "set up Celtics vs Knicks then validate"}],
    ))

    assert result["verdict"] is None  # never reached the validate node
    assert result["trade"].assets == []


def test_recursion_limit_guards_runaway_loop():
    catalog = make_catalog()
    # Always re-adds the same player -> "already in trade" error forever.
    always_add_same_player = FakeLLMClient([
        tool_call_msg(("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}))
        for _ in range(50)
    ])
    with pytest.raises(GraphRecursionError):
        asyncio.run(run_turn(
            trade=TradeState(team_ids=[2, 20]),
            catalog=catalog,
            provider=MockProvider(catalog),
            llm=always_add_same_player,
            messages=[{"role": "user", "content": "add Queta"}],
            recursion_limit=6,
        ))
