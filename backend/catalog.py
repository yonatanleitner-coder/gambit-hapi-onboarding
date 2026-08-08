"""Preloaded team/player/draft-pick catalog + local name->id resolution.

Loaded once per session from GET /teams, /players, /draft-picks (ai-plan.md
§3, §7) so the only per-turn network call the harness makes is
POST /trades/validate. Resolution never hits the network.
"""

import asyncio
import difflib
import re

import httpx
from pydantic import BaseModel

from .config import BBALL_GM_BASE

AUTO_CUTOFF = 0.75  # single close match at/above this: resolve silently
SUGGEST_CUTOFF = 0.4  # below AUTO_CUTOFF but above this: ask for disambiguation

ORDINAL_TO_ROUND = {
    "1": 1, "1st": 1, "first": 1,
    "2": 2, "2nd": 2, "second": 2,
}
PICK_YEAR_RE = re.compile(r"(19|20)\d{2}")


class Team(BaseModel):
    id: int
    name: str
    abbreviation: str
    city: str
    totalSalary: int
    capSpace: int
    isOverCap: bool
    isOverLuxuryTax: bool
    isOverFirstApron: bool
    isOverSecondApron: bool

    @property
    def full_name(self) -> str:
        return f"{self.city} {self.name}"


class Player(BaseModel):
    id: int
    name: str
    teamId: int
    teamName: str
    salary: int
    noTradeClause: bool
    signingStatus: str


class Pick(BaseModel):
    id: int
    originalTeamId: int
    originalTeamName: str
    currentTeamId: int
    currentTeamName: str
    year: int
    round: int
    isTradable: bool
    protectionDetails: str | None = None

    @property
    def descriptor(self) -> str:
        ordinal = "1st" if self.round == 1 else "2nd"
        if self.originalTeamId == self.currentTeamId:
            return f"{self.year} {ordinal}"
        return f"{self.year} {ordinal} (via {self.originalTeamName})"


class ResolutionError(BaseModel):
    error: str
    suggestions: list[str] = []


def resolve_choice(query: str, choices: dict[str, str]) -> str | ResolutionError:
    """choices: normalized-name -> original label. Returns the matched
    normalized key, or a ResolutionError with human-readable suggestions."""
    q = query.strip().lower()
    if q in choices:
        return q
    contains = [k for k in choices if q in k]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        return ResolutionError(
            error=f"multiple matches for '{query}'",
            suggestions=[choices[c] for c in contains[:5]],
        )
    # Short candidates (e.g. 3-letter team abbreviations) produce unreliable
    # SequenceMatcher ratios by coincidence of overlapping letters — exact
    # match and substring containment (above) already cover them; fuzzy
    # scoring only makes sense against longer names.
    fuzzy_pool = [k for k in choices if len(k) >= 5]
    close = difflib.get_close_matches(q, fuzzy_pool, n=3, cutoff=SUGGEST_CUTOFF)
    if close and difflib.SequenceMatcher(None, q, close[0]).ratio() >= AUTO_CUTOFF:
        return close[0]
    return ResolutionError(
        error=f"no match for '{query}'",
        suggestions=[choices[c] for c in close],
    )


class Catalog:
    def __init__(self, teams: list[Team], players: list[Player], picks: list[Pick]):
        self.teams = {t.id: t for t in teams}
        self.players = {p.id: p for p in players}
        self.picks = {p.id: p for p in picks}

    @classmethod
    async def load(cls, client: httpx.AsyncClient) -> "Catalog":
        async def get(path: str) -> list[dict]:
            resp = await client.get(f"{BBALL_GM_BASE}{path}", timeout=10)
            resp.raise_for_status()
            return resp.json()

        teams_resp, players_resp, picks_resp = await asyncio.gather(
            get("/teams"), get("/players"), get("/draft-picks")
        )
        teams = [Team(**t) for t in teams_resp]
        players = [Player(**p) for p in players_resp]
        picks = [Pick(**p) for p in picks_resp]
        return cls(teams, players, picks)

    def resolve_team(self, query: str) -> Team | ResolutionError:
        choices = {}
        for t in self.teams.values():
            choices[t.name.lower()] = t.full_name
            choices[t.full_name.lower()] = t.full_name
            choices[t.abbreviation.lower()] = t.full_name
        match = resolve_choice(query, choices)
        if isinstance(match, ResolutionError):
            return match
        label = choices[match]
        for t in self.teams.values():
            if t.full_name == label:
                return t
        return ResolutionError(error=f"no match for '{query}'")

    def resolve_player(self, query: str, team_id: int | None = None) -> Player | ResolutionError:
        pool = self.players.values()
        if team_id is not None:
            pool = [p for p in pool if p.teamId == team_id]
        choices = {p.name.lower(): p.name for p in pool}
        match = resolve_choice(query, choices)
        if isinstance(match, ResolutionError):
            return match
        label = choices[match]
        for p in pool:
            if p.name == label:
                return p
        return ResolutionError(error=f"no match for '{query}'")

    def resolve_pick(self, query: str, team_id: int) -> Pick | ResolutionError:
        team_picks = [p for p in self.picks.values() if p.currentTeamId == team_id]
        year_match = PICK_YEAR_RE.search(query)
        round_num = None
        q_lower = query.lower()
        for token, rnd in ORDINAL_TO_ROUND.items():
            if token in q_lower.split():
                round_num = rnd
                break
        if year_match is None or round_num is None:
            return ResolutionError(
                error=f"couldn't parse pick descriptor '{query}' (expected e.g. '2027 first')",
                suggestions=[p.descriptor for p in team_picks],
            )
        year = int(year_match.group())
        for p in team_picks:
            if p.year == year and p.round == round_num:
                return p
        return ResolutionError(
            error=f"no {year} round-{round_num} pick held by this team",
            suggestions=[p.descriptor for p in team_picks],
        )

