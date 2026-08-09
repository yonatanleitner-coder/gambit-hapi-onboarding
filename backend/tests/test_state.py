from backend.state import Asset, Phase, TradeState


def test_phase_empty_with_no_teams():
    assert TradeState().phase() == Phase.EMPTY


def test_phase_empty_with_only_one_team():
    assert TradeState(team_ids=[2]).phase() == Phase.EMPTY


def test_phase_teams_set_with_no_assets():
    assert TradeState(team_ids=[2, 20]).phase() == Phase.TEAMS_SET


def test_phase_has_assets_once_one_exists():
    state = TradeState(team_ids=[2, 20], assets=[
        Asset(kind="player", asset_id=1, name="X", from_team_id=2, to_team_id=20),
    ])
    assert state.phase() == Phase.HAS_ASSETS


def test_projection_groups_by_team_and_kind():
    state = TradeState(team_ids=[2, 20], assets=[
        Asset(kind="player", asset_id=100, name="A", from_team_id=2, to_team_id=20),
        Asset(kind="player", asset_id=200, name="B", from_team_id=20, to_team_id=2),
        Asset(kind="pick", asset_id=300, name="2027 1st", from_team_id=2, to_team_id=20),
    ])
    legs = {leg.teamId: leg for leg in state.to_validate_request().teams}

    assert legs[2].sendingPlayerIds == [100]
    assert legs[2].receivingPlayerIds == [200]
    assert legs[2].sendingPickIds == [300]
    assert legs[2].receivingPickIds == []

    assert legs[20].sendingPlayerIds == [200]
    assert legs[20].receivingPlayerIds == [100]
    assert legs[20].sendingPickIds == []
    assert legs[20].receivingPickIds == [300]


def test_destination_mutation_is_reflected_in_projection():
    # route_pick (task 5) flips Asset.to_team_id in place; the projection
    # must pick that up without any other state change — a single field
    # write is what makes routing atomic (ai-plan.md §2).
    pick = Asset(kind="pick", asset_id=300, name="2027 1st", from_team_id=2, to_team_id=20)
    state = TradeState(team_ids=[2, 3, 20], assets=[pick])
    assert {leg.teamId: leg.receivingPickIds for leg in state.to_validate_request().teams} == {
        2: [], 3: [], 20: [300],
    }

    pick.to_team_id = 3
    assert {leg.teamId: leg.receivingPickIds for leg in state.to_validate_request().teams} == {
        2: [], 3: [300], 20: [],
    }
