import pytest
from pydantic import ValidationError

from backend.contracts import (
    AddPlayerArgs,
    ApiHardError,
    RequestVerdictArgs,
    SetTeamsArgs,
    ValidateRequest,
    Verdict,
)


def test_set_teams_args_requires_both_teams():
    with pytest.raises(ValidationError):
        SetTeamsArgs(team_a="Celtics")


def test_add_player_args_valid():
    args = AddPlayerArgs(player="Jaylen Brown", from_team="Celtics", to_team="Knicks")
    assert args.to_team == "Knicks"


def test_request_verdict_args_takes_no_fields():
    RequestVerdictArgs()


def test_validate_request_accepts_dict_legs():
    req = ValidateRequest(teams=[
        {"teamId": 2, "sendingPlayerIds": [1], "receivingPlayerIds": [2],
         "sendingPickIds": [], "receivingPickIds": []},
        {"teamId": 20, "sendingPlayerIds": [2], "receivingPlayerIds": [1],
         "sendingPickIds": [], "receivingPickIds": []},
    ])
    assert len(req.teams) == 2


def test_verdict_parses_the_live_illegal_shape():
    # Matches the actual 200 {isValid:false} response captured in the task 1
    # spike (docs/end-of-session.md) -- guards against API drift silently.
    payload = {
        "isValid": False,
        "summary": "Trade is invalid. New York Knicks do not satisfy salary matching requirements.",
        "appliedRules": ["NBA CBA 2023 (2026-27 season) — Art. VII §6(j) Traded Player Exception"],
        "teams": [
            {"teamId": 20, "teamName": "New York Knicks", "salaryOut": 3876529,
             "salaryIn": 54126380, "netSalaryChange": 50249851, "newTotalSalary": 267813768,
             "newCapStatus": "Over Second Apron", "allowances": [],
             "violations": ["Hard cap violation: ..."], "isValid": False},
        ],
    }
    verdict = Verdict(**payload)
    assert verdict.isValid is False
    assert verdict.teams[0].violations


def test_api_hard_error_accepts_opaque_zod_string():
    err = ApiHardError(error='[{"code":"too_small","path":["teams"]}]')
    assert "too_small" in err.error
