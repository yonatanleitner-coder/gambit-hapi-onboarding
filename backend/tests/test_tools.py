from backend.catalog import Catalog, Pick, Player, Team
from backend.state import Asset, Phase, TradeState
from backend.tools import EXECUTORS, execute_tool, tools_for_phase

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


def new_state() -> TradeState:
    return TradeState()


def test_set_teams_success():
    state, catalog = new_state(), make_catalog()
    result = execute_tool("set_teams", {"team_a": "Celtics", "team_b": "nyk"}, state, catalog)
    assert "error" not in result
    assert state.team_ids == [2, 20]
    assert result["snapshot"]["phase"] == Phase.TEAMS_SET.value


def test_set_teams_unknown_team_does_not_mutate():
    state, catalog = new_state(), make_catalog()
    result = execute_tool("set_teams", {"team_a": "Celtics", "team_b": "Lakers"}, state, catalog)
    assert "error" in result
    assert state.team_ids == []


def test_set_teams_same_team_twice_rejected():
    state, catalog = new_state(), make_catalog()
    result = execute_tool("set_teams", {"team_a": "Celtics", "team_b": "BOS"}, state, catalog)
    assert "error" in result
    assert state.team_ids == []


def test_add_player_success_and_projection():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    result = execute_tool("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    assert "error" not in result
    assert len(state.assets) == 1
    assert state.assets[0].asset_id == 16998
    assert result["added"][0]["name"] == "Neemias Queta"
    assert result["snapshot"]["phase"] == Phase.HAS_ASSETS.value


def test_add_player_wrong_team_scoping_fails():
    # Drummond plays for the Knicks, not the Celtics -- must not resolve
    # under from_team="Celtics" even though he's in the global catalog.
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    result = execute_tool("add_player", {"player": "Drummond", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    assert "error" in result
    assert state.assets == []


def test_add_player_duplicate_rejected():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    execute_tool("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    result = execute_tool("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    assert "error" in result
    assert len(state.assets) == 1


def test_add_pick_uses_descriptor_as_name():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    result = execute_tool("add_pick", {"pick": "2027 first", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    assert "error" not in result
    assert state.assets[0].name == "2027 1st (via Knicks)"


def test_route_pick_changes_destination():
    pick_asset = Asset(kind="pick", asset_id=12062, name="2027 1st (via Knicks)",
                        from_team_id=2, to_team_id=20)
    state = TradeState(team_ids=[2, 3, 20], assets=[pick_asset])
    catalog = make_catalog()
    result = execute_tool("route_pick", {"pick": "2027 first", "to_team": "Celtics"}, state, catalog)
    # routing to the pick's own origin team should be rejected
    assert "error" in result
    assert pick_asset.to_team_id == 20  # unchanged


def test_route_pick_not_found_returns_suggestions():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    result = execute_tool("route_pick", {"pick": "2030 second", "to_team": "Knicks"}, state, catalog)
    assert "error" in result


def test_remove_player_success_and_not_found():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    execute_tool("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    result = execute_tool("remove_player", {"player": "Queta"}, state, catalog)
    assert "error" not in result
    assert state.assets == []

    result = execute_tool("remove_player", {"player": "Queta"}, state, catalog)
    assert "error" in result


def test_request_verdict_blocked_before_has_assets():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    result = execute_tool("request_verdict", {}, state, catalog)
    assert "error" in result


def test_request_verdict_allowed_once_has_assets():
    state, catalog = TradeState(team_ids=[2, 20]), make_catalog()
    execute_tool("add_player", {"player": "Queta", "from_team": "Celtics", "to_team": "Knicks"}, state, catalog)
    result = execute_tool("request_verdict", {}, state, catalog)
    assert "error" not in result


def test_execute_tool_unknown_name():
    result = execute_tool("delete_everything", {}, TradeState(), make_catalog())
    assert "error" in result


def test_execute_tool_invalid_args_recovers_gracefully():
    # missing required 'to_team' -- pydantic validation failure, not a crash
    result = execute_tool("add_player", {"player": "Queta", "from_team": "Celtics"}, TradeState(team_ids=[2, 20]), make_catalog())
    assert "error" in result


def test_tools_for_phase_matches_gating_table():
    assert {t["name"] for t in tools_for_phase(Phase.EMPTY)} == {"set_teams"}
    assert {t["name"] for t in tools_for_phase(Phase.TEAMS_SET)} == {"add_player", "add_pick"}
    assert {t["name"] for t in tools_for_phase(Phase.HAS_ASSETS)} == set(EXECUTORS) - {"set_teams"}


def test_tools_for_phase_schema_has_input_properties():
    schemas = {t["name"]: t for t in tools_for_phase(Phase.TEAMS_SET)}
    assert "player" in schemas["add_player"]["input_schema"]["properties"]
