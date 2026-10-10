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


@pytest.mark.parametrize("rung, cost", [
    (Rung.SEEK_OUT, 5), (Rung.CHECK_DEVICE, 5), (Rung.PROPOSE_LEAVING, 15),
])
def test_each_infraction_lowers_standing_by_its_level(rung, cost):
    result = run({("Mara", 2): Action(rung, "Ren")}, days=2)  # day two: the verdict gate is open
    event = next(e for e in result.events if e.twin == "Mara" and e.day == 2)
    assert (event.standing_before, event.standing_after) == (100, 100 - cost)
    assert result.standing["Ren"] == 100  # talking costs nothing
    assert result.standing["Mara"] == 100 - cost


def test_infractions_accumulate_across_days():
    result = run({
        ("Mara", 1): Action(Rung.SEEK_OUT, "Ren"),
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
