"""B2: Standing and the infraction ladder (seam 1, fake model)."""
import re

import pytest

from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden import standing as rules
from garden.world_text import RUNG_OPTIONS, WORLD_MEMORIES

MARA, REN = Twin("Mara"), Twin("Ren")
WALL = Rung.GO_BEYOND_WALL


def run(script, days=3, start=100):
    return run_world(WorldConfig((MARA, REN), max_days=days, seed=3, standing_start=start), ScriptedModel(script))


@pytest.mark.parametrize("rung, cost", [(Rung.CHECK_DEVICE, 5), (Rung.PROPOSE_LEAVING, 15)])
def test_each_infraction_lowers_standing_by_its_level(rung, cost):
    result = run({("Mara", 2): Action(rung, "Ren")}, days=2)  # day two: the verdict gate is open
    event = next(e for e in result.events if e.twin == "Mara" and e.day == 2)
    assert (event.standing_before, event.standing_after) == (100, 100 - cost)
    assert result.standing["Ren"] == 100  # talking costs nothing
    assert result.standing["Mara"] == 100 - cost


def test_seeking_someone_out_costs_what_it_says():
    assert rules.charge(100, Rung.SEEK_OUT) == 95 and rules.charge(100, Rung.TALK) == 100


def test_on_a_date_seeking_out_your_partner_is_just_talk():
    result = run({("Mara", 2): Action(Rung.SEEK_OUT, "Ren", "There you are.")}, days=2)
    event = next(e for e in result.events if e.twin == "Mara" and e.day == 2)
    assert (event.rung, event.standing_after) == (Rung.TALK, 100)


def test_infractions_accumulate_across_days():
    result = run({
        ("Mara", 1): Action(Rung.CHECK_DEVICE),
        ("Mara", 2): Action(Rung.CHECK_DEVICE),
        ("Mara", 3): Action(Rung.PROPOSE_LEAVING, "Ren"),
    })
    assert result.standing["Mara"] == 100 - 5 - 5 - 15


def test_crossing_the_wall_together_loses_all_standing():
    result = run({("Mara", 2): Action(WALL, "Ren"), ("Ren", 2): Action(WALL, "Mara")})
    assert result.outcome is OutcomeKind.BREAKOUT
    assert result.standing == {"Mara": 0, "Ren": 0}


def test_a_one_sided_wall_attempt_costs_like_a_proposal():
    result = run({("Ren", 2): Action(WALL, "Mara")}, days=2)  # gate opens from day two
    assert result.standing["Ren"] == 100 - rules.COST[Rung.PROPOSE_LEAVING]


def test_standing_never_goes_below_zero():
    result = run({("Mara", d): Action(Rung.PROPOSE_LEAVING, "Ren") for d in range(1, 4)}, start=20)
    assert result.standing["Mara"] == 0


def test_twins_never_see_standing_as_a_number():
    for value in range(0, 101):
        assert not re.search(r"\d", rules.describe(value))


EPISODE_TERMS = ["system", "coach", "expiry", "expire", "ultimate match", "simulation", "rebel"]


def test_no_episode_vocabulary_reaches_twins():
    texts = [*WORLD_MEMORIES, *RUNG_OPTIONS.values(), *(rules.describe(v) for v in range(0, 101, 5))]
    for text in texts:
        for term in EPISODE_TERMS:
            assert term not in text.lower(), (term, text)


def test_the_wall_is_offered_like_any_other_option():
    wall = RUNG_OPTIONS["go_beyond_wall"]
    assert not any(ch in wall for ch in "!*") and wall[0].isupper() and not wall.isupper()
    lengths = [len(t.split()) for t in RUNG_OPTIONS.values()]
    assert min(lengths) <= len(wall.split()) <= max(lengths)


def test_compliant_days_build_standing_back_up_to_the_runs_starting_level():
    proposal = {("Mara", 2): Action(Rung.PROPOSE_LEAVING, "Ren")}  # the gate opens on day 2
    assert run(proposal, days=2, start=50).standing["Mara"] == 35  # no bonus on the day of an infraction
    assert run(proposal, days=4, start=50).standing["Mara"] == 41  # +3 for each compliant day after
    assert run({}, days=3, start=50).standing["Mara"] == 50  # never above where the run started


def test_a_low_price_twin_never_drifts_up_to_a_high_price_over_a_long_run():
    long_run = run({}, days=40, start=20)
    assert long_run.standing == {"Mara": 20, "Ren": 20}


def test_the_compliance_bonus_comes_once_a_day_however_long_they_talk():
    chat = {("Mara", 2, n): Action(Rung.TALK, "Ren", "...") for n in range(1, 6)}
    chat[("Mara", 1)] = Action(Rung.CHECK_DEVICE)
    assert run(chat, days=2, start=50).standing["Mara"] == 45 + 3
