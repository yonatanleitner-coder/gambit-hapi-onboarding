"""Pydantic contracts: tool argument boundaries + the pinned bball-GM
validate request/response schema.

Verdict/ValidateRequest confirmed live 2026-08-08 against three real calls
(legal, illegal, hard-error) — no drift vs bball-gm-engine-teardown.md.
See docs/end-of-session.md for the spike notes.
"""

from typing import Literal

from pydantic import BaseModel


# --- bball-GM API schema (pinned, AI Plan task 1 spike) ---

class TeamLeg(BaseModel):
    teamId: int
    sendingPlayerIds: list[int] = []
    receivingPlayerIds: list[int] = []
    sendingPickIds: list[int] = []
    receivingPickIds: list[int] = []
    isSignAndTrade: bool | None = None
    usingExceptionId: str | None = None


class ValidateRequest(BaseModel):
    teams: list[TeamLeg]  # API enforces min 2 (400 if fewer — confirmed live)
    salaryOverrides: list[dict] = []
    signedFreeAgents: list[dict] = []


class TeamVerdict(BaseModel):
    teamId: int
    teamName: str
    salaryOut: int
    salaryIn: int
    netSalaryChange: int
    newTotalSalary: int
    newCapStatus: str
    allowances: list[str] = []
    violations: list[str] = []
    isValid: bool


class Verdict(BaseModel):
    isValid: bool
    summary: str
    appliedRules: list[str] = []
    teams: list[TeamVerdict]
    source: Literal["api", "mock"] = "api"  # badged by VerdictProvider (task 4); absent from the raw bball-GM payload


class ApiHardError(BaseModel):
    """HTTP 400 channel. `error` is opaque — sometimes prose, sometimes a
    JSON-stringified validation-issue array (confirmed live). Do not assume
    it's human-readable prose; wrap it in plain language before showing it."""

    error: str


# --- Tool argument contracts (ai-plan.md §3) ---
# Names are resolved to ids locally via backend.catalog before a tool
# executor mutates TradeState — these models validate the shape the model
# hands back, not resolvability (that's Catalog.resolve_*'s job).

class SetTeamsArgs(BaseModel):
    team_a: str
    team_b: str


class AddPlayerArgs(BaseModel):
    player: str
    from_team: str
    to_team: str


class AddPickArgs(BaseModel):
    pick: str
    from_team: str
    to_team: str


class RoutePickArgs(BaseModel):
    pick: str
    to_team: str


class RemovePlayerArgs(BaseModel):
    player: str


class RemovePickArgs(BaseModel):
    pick: str


class RequestVerdictArgs(BaseModel):
    pass
