import asyncio

import httpx
import pytest

from backend.catalog import Catalog, Player, Team
from backend.contracts import ValidateRequest
from backend.providers import (
    CAP,
    FIRST_APRON,
    LUXURY_TAX,
    SECOND_APRON,
    BballGmProvider,
    HardRuleViolation,
    MockProvider,
    ProviderUnavailable,
    _cap_status,
)

# Same real teams/players as the AI Plan task 1 API spike, so MockProvider's
# outcomes can be checked against the live verdicts captured there.
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
    Player(id=17329, name="Paul George", teamId=2, teamName="Celtics",
           salary=54126380, noTradeClause=False, signingStatus="active"),
]


def make_catalog() -> Catalog:
    return Catalog(TEAMS, PLAYERS, [])


def test_cap_status_boundaries():
    assert _cap_status(CAP - 1) == "Under Cap"
    assert _cap_status(CAP) == "Over Cap"
    assert _cap_status(LUXURY_TAX) == "Over Luxury Tax"
    assert _cap_status(FIRST_APRON) == "Over First Apron"
    assert _cap_status(SECOND_APRON) == "Over Second Apron"


def test_mock_provider_legal_trade_matches_live_verdict():
    # Live spike (docs/end-of-session.md): Queta<->Drummond was 200 {isValid:true}.
    req = ValidateRequest(teams=[
        {"teamId": 2, "sendingPlayerIds": [16998], "receivingPlayerIds": [17338],
         "sendingPickIds": [], "receivingPickIds": []},
        {"teamId": 20, "sendingPlayerIds": [17338], "receivingPlayerIds": [16998],
         "sendingPickIds": [], "receivingPickIds": []},
    ])
    verdict = asyncio.run(MockProvider(make_catalog()).validate(req))
    assert verdict.source == "mock"
    assert verdict.isValid is True


def test_mock_provider_illegal_trade_matches_live_verdict():
    # Live spike: Paul George for Drummond was 200 {isValid:false}, Knicks failing.
    req = ValidateRequest(teams=[
        {"teamId": 2, "sendingPlayerIds": [17329], "receivingPlayerIds": [17338],
         "sendingPickIds": [], "receivingPickIds": []},
        {"teamId": 20, "sendingPlayerIds": [17338], "receivingPlayerIds": [17329],
         "sendingPickIds": [], "receivingPickIds": []},
    ])
    verdict = asyncio.run(MockProvider(make_catalog()).validate(req))
    assert verdict.isValid is False
    knicks = next(t for t in verdict.teams if t.teamId == 20)
    assert knicks.isValid is False
    assert knicks.violations


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_bball_gm_provider_parses_200_and_badges_api_source():
    def handler(request):
        return httpx.Response(200, json={
            "isValid": True, "summary": "ok", "appliedRules": [],
            "teams": [{"teamId": 2, "teamName": "Boston Celtics", "salaryOut": 1,
                       "salaryIn": 1, "netSalaryChange": 0, "newTotalSalary": 1,
                       "newCapStatus": "Under Cap", "allowances": [], "violations": [], "isValid": True}],
        })

    async def run():
        async with _client(handler) as client:
            req = ValidateRequest(teams=[{"teamId": 2}, {"teamId": 20}])
            return await BballGmProvider(client).validate(req)

    verdict = asyncio.run(run())
    assert verdict.source == "api"
    assert verdict.isValid is True


def test_bball_gm_provider_omits_none_fields_from_request_body():
    # Regression: the live API rejects an explicit `null` for optional
    # fields like isSignAndTrade (confirmed against the real API) --
    # model_dump() must exclude_none, not just omit unset fields.
    captured = {}

    def handler(request):
        captured["body"] = request.content
        return httpx.Response(200, json={
            "isValid": True, "summary": "ok", "appliedRules": [],
            "teams": [{"teamId": 2, "teamName": "x", "salaryOut": 0, "salaryIn": 0,
                       "netSalaryChange": 0, "newTotalSalary": 0, "newCapStatus": "Under Cap",
                       "allowances": [], "violations": [], "isValid": True}],
        })

    async def run():
        async with _client(handler) as client:
            req = ValidateRequest(teams=[{"teamId": 2}, {"teamId": 20}])
            await BballGmProvider(client).validate(req)

    asyncio.run(run())
    assert b"null" not in captured["body"]


def test_bball_gm_provider_raises_hard_rule_violation_on_400():
    def handler(request):
        return httpx.Response(400, json={"error": "Stepien rule violation"})

    async def run():
        async with _client(handler) as client:
            req = ValidateRequest(teams=[{"teamId": 2}, {"teamId": 20}])
            await BballGmProvider(client).validate(req)

    with pytest.raises(HardRuleViolation) as exc_info:
        asyncio.run(run())
    assert "Stepien" in exc_info.value.api_error.error


def test_bball_gm_provider_raises_unavailable_on_unexpected_status():
    def handler(request):
        return httpx.Response(500, text="boom")

    async def run():
        async with _client(handler) as client:
            req = ValidateRequest(teams=[{"teamId": 2}, {"teamId": 20}])
            await BballGmProvider(client).validate(req)

    with pytest.raises(ProviderUnavailable):
        asyncio.run(run())


def test_bball_gm_provider_raises_unavailable_on_network_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    async def run():
        async with _client(handler) as client:
            req = ValidateRequest(teams=[{"teamId": 2}, {"teamId": 20}])
            await BballGmProvider(client).validate(req)

    with pytest.raises(ProviderUnavailable):
        asyncio.run(run())
