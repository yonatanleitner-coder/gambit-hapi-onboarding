"""VerdictProvider: real bball-GM API + deterministic mock fallback
(ai-plan.md §5).

BballGmProvider is the source of legality truth. MockProvider is a
simplified, deterministic salary-matching approximation -- used when the
real API is unreachable, and for golden cases / tests (PROVIDER=mock) so
they don't depend on network or on real CBA logic changing. It is never
authoritative (bball-gm-engine-teardown.md: "don't build a trade-legality
engine from scratch") -- callers must badge Verdict.source and show it.
"""

from typing import Protocol

import httpx

from .catalog import Catalog, Team
from .config import BBALL_GM_BASE
from .contracts import ApiHardError, TeamVerdict, ValidateRequest, Verdict

# Cap constants (2026-27 season), bball-gm-engine-teardown.md.
CAP = 165_000_000
LUXURY_TAX = 201_000_000
FIRST_APRON = 209_000_000
SECOND_APRON = 222_000_000
TRADE_MATCH_FLAT_ADDON = 9_400_000
TRADE_MATCH_ADDON = 250_000


class ProviderUnavailable(Exception):
    """Real API unreachable, timed out, or returned an unexpected shape.
    Triggers MockProvider fallback (ai-plan.md §5)."""


class HardRuleViolation(Exception):
    """HTTP 400 -- a hard CBA rule (Stepien, stretch, schema) or malformed
    request. NOT a fallback trigger: the API is working and answering
    correctly. human-plan.md's two failure channels get two distinct,
    plain-language messages -- this is the second one."""

    def __init__(self, api_error: ApiHardError):
        self.api_error = api_error
        super().__init__(api_error.error)


class VerdictProvider(Protocol):
    async def validate(self, req: ValidateRequest) -> Verdict: ...


class BballGmProvider:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def validate(self, req: ValidateRequest) -> Verdict:
        try:
            resp = await self._client.post(
                f"{BBALL_GM_BASE}/trades/validate",
                # exclude_none: the API's schema rejects explicit `null` for
                # optional fields like isSignAndTrade (confirmed live) --
                # they must be omitted, not nulled.
                json=req.model_dump(exclude_none=True),
                timeout=6.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"bball-GM API request failed: {exc}") from exc

        if resp.status_code == 200:
            return Verdict(**resp.json(), source="api")
        if resp.status_code == 400:
            raise HardRuleViolation(ApiHardError(**resp.json()))
        raise ProviderUnavailable(f"bball-GM API returned unexpected status {resp.status_code}")


def _cap_status(total_salary: int) -> str:
    if total_salary >= SECOND_APRON:
        return "Over Second Apron"
    if total_salary >= FIRST_APRON:
        return "Over First Apron"
    if total_salary >= LUXURY_TAX:
        return "Over Luxury Tax"
    if total_salary >= CAP:
        return "Over Cap"
    return "Under Cap"


def _max_incoming(team: Team, salary_out: int) -> tuple[int, str]:
    """Simplified approximation of bball-gm-engine-teardown.md's matching
    tiers -- deliberately not exact CBA math (out of scope)."""
    if team.isOverSecondApron:
        return salary_out, "second apron: cannot increase net salary"
    if team.isOverFirstApron:
        return salary_out, "first apron: 100% of outgoing"
    if team.isOverCap:
        expanded = max(salary_out * 1.25 + TRADE_MATCH_ADDON,
                        min(salary_out * 2 + TRADE_MATCH_ADDON, salary_out + TRADE_MATCH_FLAT_ADDON))
        capped = min(expanded, FIRST_APRON - (team.totalSalary - salary_out))
        return int(capped), "expanded bands, capped at first apron"
    return team.capSpace + salary_out + TRADE_MATCH_ADDON, "cap room + outgoing + $250K"


class MockProvider:
    def __init__(self, catalog: Catalog):
        self._catalog = catalog

    async def validate(self, req: ValidateRequest) -> Verdict:
        team_verdicts = []
        for leg in req.teams:
            team = self._catalog.teams[leg.teamId]
            salary_out = sum(self._catalog.players[pid].salary for pid in leg.sendingPlayerIds)
            salary_in = sum(self._catalog.players[pid].salary for pid in leg.receivingPlayerIds)
            new_total = team.totalSalary - salary_out + salary_in

            max_incoming, tier_note = _max_incoming(team, salary_out)
            is_valid = salary_in <= max_incoming
            violations = [] if is_valid else [
                f"{team.full_name} salary matching exceeded: sending "
                f"${salary_out / 1e6:.1f}M, receiving ${salary_in / 1e6:.1f}M "
                f"(limit ${max_incoming / 1e6:.1f}M, {tier_note})"
            ]
            allowances = [] if not is_valid else [
                f"Simplified match ({tier_note}): can receive up to ${max_incoming / 1e6:.1f}M"
            ]
            team_verdicts.append(TeamVerdict(
                teamId=team.id, teamName=team.full_name, salaryOut=salary_out,
                salaryIn=salary_in, netSalaryChange=salary_in - salary_out,
                newTotalSalary=new_total, newCapStatus=_cap_status(new_total),
                allowances=allowances, violations=violations, isValid=is_valid,
            ))

        overall_valid = all(t.isValid for t in team_verdicts)
        failing = [t.teamName for t in team_verdicts if not t.isValid]
        summary = (
            "Trade is valid under simplified mock rules."
            if overall_valid else
            f"Trade is invalid. {', '.join(failing)} do not satisfy simplified salary matching."
        )
        return Verdict(
            isValid=overall_valid,
            summary=summary,
            appliedRules=["MockProvider: simplified salary-matching approximation, not authoritative CBA logic"],
            teams=team_verdicts,
            source="mock",
        )
