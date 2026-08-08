from backend.catalog import Catalog, Pick, Player, ResolutionError, Team

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
    Player(id=16991, name="Jaylen Brown", teamId=2, teamName="Celtics",
           salary=57078728, noTradeClause=False, signingStatus="active"),
]
PICKS = [
    Pick(id=12062, originalTeamId=20, originalTeamName="Knicks",
         currentTeamId=2, currentTeamName="Celtics", year=2027, round=1,
         isTradable=True),
    # Two distinct picks, same year+round, both currently held by Boston --
    # a real, live-confirmed scenario (a team's own pick plus another
    # team's for the same draft slot).
    Pick(id=12100, originalTeamId=2, originalTeamName="Celtics",
         currentTeamId=2, currentTeamName="Celtics", year=2031, round=1,
         isTradable=True),
    Pick(id=12413, originalTeamId=23, originalTeamName="76ers",
         currentTeamId=2, currentTeamName="Celtics", year=2031, round=1,
         isTradable=True),
]


def make_catalog() -> Catalog:
    return Catalog(TEAMS, PLAYERS, PICKS)


def test_resolve_team_exact():
    cat = make_catalog()
    assert cat.resolve_team("Celtics").id == 2


def test_resolve_team_by_abbreviation():
    cat = make_catalog()
    assert cat.resolve_team("nyk").id == 20


def test_resolve_team_fuzzy_typo():
    cat = make_catalog()
    result = cat.resolve_team("Celtcs")
    assert isinstance(result, Team) and result.id == 2


def test_resolve_team_no_match_returns_suggestions():
    cat = make_catalog()
    result = cat.resolve_team("Lakers")
    assert isinstance(result, ResolutionError)


def test_resolve_player_scoped_to_team():
    cat = make_catalog()
    assert cat.resolve_player("Queta", team_id=2).id == 16998
    result = cat.resolve_player("Queta", team_id=20)
    assert isinstance(result, ResolutionError)


def test_resolve_player_high_confidence_typo_auto_resolves():
    # Deliberate deviation from ai-plan.md §3's worked example (which treats
    # this as a resolution error requiring disambiguation) — human chose to
    # keep silent auto-resolve above the fuzzy-match confidence threshold.
    # See docs/end-of-session.md "Human guidance given".
    cat = make_catalog()
    result = cat.resolve_player("Jaylen Browne")
    assert isinstance(result, Player) and result.id == 16991


def test_resolve_player_low_confidence_typo_suggests():
    cat = make_catalog()
    result = cat.resolve_player("Drmond", team_id=20)  # ratio ~0.6: below auto-resolve, above suggest cutoff
    assert isinstance(result, ResolutionError)
    assert result.suggestions == ["Andre Drummond"]


def test_resolve_pick_by_descriptor():
    cat = make_catalog()
    pick = cat.resolve_pick("2027 first", team_id=2)
    assert isinstance(pick, Pick) and pick.id == 12062
    assert pick.descriptor == "2027 1st (via Knicks)"


def test_resolve_pick_ambiguous_year_round_returns_error_not_first_match():
    cat = make_catalog()
    result = cat.resolve_pick("2031 first", team_id=2)
    assert isinstance(result, ResolutionError)
    assert sorted(result.suggestions) == ["2031 1st", "2031 1st (via 76ers)"]


def test_resolve_pick_tolerates_natural_phrasing():
    # A model asked to move "their 2027 first-round pick" may pass that
    # phrasing straight through rather than normalizing to "2027 first" --
    # word-boundary matching must still find "first" inside "first-round".
    cat = make_catalog()
    pick = cat.resolve_pick("their 2027 first-round pick", team_id=2)
    assert isinstance(pick, Pick) and pick.id == 12062


def test_resolve_pick_wrong_team_suggests_available():
    cat = make_catalog()
    result = cat.resolve_pick("2027 first", team_id=20)
    assert isinstance(result, ResolutionError)
    assert result.suggestions == []  # Knicks hold no picks in this fixture


def test_resolve_pick_unparseable_descriptor():
    cat = make_catalog()
    result = cat.resolve_pick("their good pick", team_id=2)
    assert isinstance(result, ResolutionError)
    assert "2027 1st" in result.suggestions[0]
