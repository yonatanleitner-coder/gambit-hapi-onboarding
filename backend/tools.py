"""Tool definitions + executors -- the only state mutators (ai-plan.md §3).

Each executor validates raw args (pydantic) -> resolves names to ids
locally via catalog.py -> mutates TradeState -> returns a state
snapshot + diff. Resolution/validation failure returns a structured error
dict, never raises: "tool errors are results, never exceptions" so the
model can see what went wrong and retry or disambiguate.
"""

from pydantic import BaseModel, ValidationError

from .catalog import Catalog, ResolutionError, resolve_choice
from .contracts import (
    AddPickArgs,
    AddPlayerArgs,
    RemovePickArgs,
    RemovePlayerArgs,
    RequestVerdictArgs,
    RoutePickArgs,
    SetTeamsArgs,
)
from .state import Asset, Phase, TradeState

# --- phase-gated tool availability (ai-plan.md §3 table) ---

TOOLS_BY_PHASE: dict[Phase, list[str]] = {
    Phase.EMPTY: ["set_teams"],
    Phase.TEAMS_SET: ["add_player", "add_pick"],
    Phase.HAS_ASSETS: [
        "add_player", "add_pick", "remove_player", "remove_pick",
        "route_pick", "request_verdict",
    ],
}

DESCRIPTIONS: dict[str, str] = {
    "set_teams": "Set the two teams involved in the trade. Only usable before any teams are set.",
    "add_player": "Add a player to the trade, moving from one team to the other.",
    "add_pick": "Add a draft pick to the trade, moving from one team to the other.",
    "route_pick": "Change which team an already-added pick is currently routed to.",
    "remove_player": "Remove a player from the trade.",
    "remove_pick": "Remove a draft pick from the trade.",
    "request_verdict": "Validate the current trade against the bball-GM engine and get a legality verdict. Requires two teams and at least one asset.",
}


def _snapshot(state: TradeState) -> dict:
    return {
        "teams": list(state.team_ids),
        "assets": [
            {"kind": a.kind, "id": a.asset_id, "name": a.name,
             "from_team_id": a.from_team_id, "to_team_id": a.to_team_id}
            for a in state.assets
        ],
        "phase": state.phase().value,
    }


def _find_asset(state: TradeState, kind: str, query: str) -> Asset | ResolutionError:
    pool = [a for a in state.assets if a.kind == kind]
    choices = {a.name.lower(): a.name for a in pool}
    match = resolve_choice(query, choices)
    if isinstance(match, ResolutionError):
        return match
    label = choices[match]
    return next(a for a in pool if a.name == label)


def exec_set_teams(state: TradeState, catalog: Catalog, args: SetTeamsArgs) -> dict:
    team_a = catalog.resolve_team(args.team_a)
    if isinstance(team_a, ResolutionError):
        return team_a.model_dump()
    team_b = catalog.resolve_team(args.team_b)
    if isinstance(team_b, ResolutionError):
        return team_b.model_dump()
    if team_a.id == team_b.id:
        return {"error": f"'{args.team_a}' and '{args.team_b}' resolved to the same team"}

    state.team_ids = [team_a.id, team_b.id]
    return {"added": [], "removed": [], "rerouted": [], "snapshot": _snapshot(state)}


def exec_add_player(state: TradeState, catalog: Catalog, args: AddPlayerArgs) -> dict:
    from_team = catalog.resolve_team(args.from_team)
    if isinstance(from_team, ResolutionError):
        return from_team.model_dump()
    to_team = catalog.resolve_team(args.to_team)
    if isinstance(to_team, ResolutionError):
        return to_team.model_dump()

    player = catalog.resolve_player(args.player, team_id=from_team.id)
    if isinstance(player, ResolutionError):
        return player.model_dump()
    if any(a.kind == "player" and a.asset_id == player.id for a in state.assets):
        return {"error": f"{player.name} is already part of this trade"}

    asset = Asset(kind="player", asset_id=player.id, name=player.name,
                  from_team_id=from_team.id, to_team_id=to_team.id, salary=player.salary)
    state.assets.append(asset)
    added = [{"kind": "player", "id": asset.asset_id, "name": asset.name,
              "from_team_id": asset.from_team_id, "to_team_id": asset.to_team_id}]
    return {"added": added, "removed": [], "rerouted": [], "snapshot": _snapshot(state)}


def exec_add_pick(state: TradeState, catalog: Catalog, args: AddPickArgs) -> dict:
    from_team = catalog.resolve_team(args.from_team)
    if isinstance(from_team, ResolutionError):
        return from_team.model_dump()
    to_team = catalog.resolve_team(args.to_team)
    if isinstance(to_team, ResolutionError):
        return to_team.model_dump()

    pick = catalog.resolve_pick(args.pick, team_id=from_team.id)
    if isinstance(pick, ResolutionError):
        return pick.model_dump()
    if any(a.kind == "pick" and a.asset_id == pick.id for a in state.assets):
        return {"error": f"{pick.descriptor} is already part of this trade"}

    # Stepien-rule / tradability is bball-GM's call, not ours (teardown.md:
    # "don't build a trade-legality engine from scratch") -- adding an
    # untradable pick is allowed here; the real API rejects it with a 400
    # at validate time and that's surfaced to the user then, not here.
    asset = Asset(kind="pick", asset_id=pick.id, name=pick.descriptor,
                  from_team_id=from_team.id, to_team_id=to_team.id, salary=None)
    state.assets.append(asset)
    added = [{"kind": "pick", "id": asset.asset_id, "name": asset.name,
              "from_team_id": asset.from_team_id, "to_team_id": asset.to_team_id}]
    return {"added": added, "removed": [], "rerouted": [], "snapshot": _snapshot(state)}


def exec_route_pick(state: TradeState, catalog: Catalog, args: RoutePickArgs) -> dict:
    asset = _find_asset(state, "pick", args.pick)
    if isinstance(asset, ResolutionError):
        return asset.model_dump()
    to_team = catalog.resolve_team(args.to_team)
    if isinstance(to_team, ResolutionError):
        return to_team.model_dump()
    if to_team.id == asset.from_team_id:
        return {"error": f"can't route {asset.name} to the team it's coming from"}

    asset.to_team_id = to_team.id
    rerouted = [{"kind": "pick", "id": asset.asset_id, "name": asset.name,
                 "from_team_id": asset.from_team_id, "to_team_id": asset.to_team_id}]
    return {"added": [], "removed": [], "rerouted": rerouted, "snapshot": _snapshot(state)}


def exec_remove_player(state: TradeState, catalog: Catalog, args: RemovePlayerArgs) -> dict:
    asset = _find_asset(state, "player", args.player)
    if isinstance(asset, ResolutionError):
        return asset.model_dump()
    state.assets.remove(asset)
    removed = [{"kind": "player", "id": asset.asset_id, "name": asset.name}]
    return {"added": [], "removed": removed, "rerouted": [], "snapshot": _snapshot(state)}


def exec_remove_pick(state: TradeState, catalog: Catalog, args: RemovePickArgs) -> dict:
    asset = _find_asset(state, "pick", args.pick)
    if isinstance(asset, ResolutionError):
        return asset.model_dump()
    state.assets.remove(asset)
    removed = [{"kind": "pick", "id": asset.asset_id, "name": asset.name}]
    return {"added": [], "removed": removed, "rerouted": [], "snapshot": _snapshot(state)}


def exec_request_verdict(state: TradeState, catalog: Catalog, args: RequestVerdictArgs) -> dict:
    # No-op mutator: request_verdict is a control-flow signal (graph.py
    # routes to the validate node when it sees this call), not a state
    # mutation. Guarded here too -- defense in depth against a hallucinated
    # call slipping through despite not being offered pre-HAS_ASSETS.
    if state.phase() != Phase.HAS_ASSETS:
        return {"error": "can't request a verdict before two teams and at least one asset are set"}
    return {"snapshot": _snapshot(state)}


EXECUTORS: dict[str, tuple[type[BaseModel], callable]] = {
    "set_teams": (SetTeamsArgs, exec_set_teams),
    "add_player": (AddPlayerArgs, exec_add_player),
    "add_pick": (AddPickArgs, exec_add_pick),
    "route_pick": (RoutePickArgs, exec_route_pick),
    "remove_player": (RemovePlayerArgs, exec_remove_player),
    "remove_pick": (RemovePickArgs, exec_remove_pick),
    "request_verdict": (RequestVerdictArgs, exec_request_verdict),
}


def tools_for_phase(phase: Phase) -> list[dict]:
    """Anthropic tool-use schema for every tool valid in `phase` -- the
    closed boundary the model literally cannot see past."""
    specs = []
    for name in TOOLS_BY_PHASE[phase]:
        args_model = EXECUTORS[name][0]
        schema = args_model.model_json_schema()
        schema.pop("title", None)
        specs.append({"name": name, "description": DESCRIPTIONS[name], "input_schema": schema})
    return specs


def execute_tool(name: str, raw_args: dict, state: TradeState, catalog: Catalog) -> dict:
    if name not in EXECUTORS:
        return {"error": f"unknown tool '{name}'"}
    args_model, fn = EXECUTORS[name]
    try:
        args = args_model(**raw_args)
    except ValidationError as exc:
        return {"error": f"invalid arguments for {name}: {exc.errors()}"}
    return fn(state, catalog, args)
