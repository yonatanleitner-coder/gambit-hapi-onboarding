"""TradeState: the single source of truth (ai-plan.md §2).

A team pair + a flat asset list, carried inside the graph state (task 5)
alongside the current phase. The validate request is projected from assets
at verdict time; route_pick (task 5's tools.py) just flips an Asset's
to_team_id in place, so routing can never be half-applied.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .contracts import TeamLeg, ValidateRequest


class Phase(str, Enum):
    EMPTY = "empty"  # no teams yet
    TEAMS_SET = "teams_set"  # two teams, no assets
    HAS_ASSETS = "has_assets"  # >=1 asset -- verdict now reachable


@dataclass
class Asset:
    kind: Literal["player", "pick"]
    asset_id: int
    name: str
    from_team_id: int
    to_team_id: int
    salary: int | None = None


@dataclass
class TradeState:
    team_ids: list[int] = field(default_factory=list)  # exactly 2 when set
    assets: list[Asset] = field(default_factory=list)

    def phase(self) -> Phase:
        if len(self.team_ids) != 2:
            return Phase.EMPTY
        if not self.assets:
            return Phase.TEAMS_SET
        return Phase.HAS_ASSETS

    def to_validate_request(self) -> ValidateRequest:
        legs = []
        for team_id in self.team_ids:
            legs.append(TeamLeg(
                teamId=team_id,
                sendingPlayerIds=[a.asset_id for a in self.assets
                                  if a.kind == "player" and a.from_team_id == team_id],
                receivingPlayerIds=[a.asset_id for a in self.assets
                                     if a.kind == "player" and a.to_team_id == team_id],
                sendingPickIds=[a.asset_id for a in self.assets
                                if a.kind == "pick" and a.from_team_id == team_id],
                receivingPickIds=[a.asset_id for a in self.assets
                                   if a.kind == "pick" and a.to_team_id == team_id],
            ))
        return ValidateRequest(teams=legs)
