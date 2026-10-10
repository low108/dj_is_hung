"""Seam 1: a simulation run, driven by the scripted fake model."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world

MARA, REN, JUN = Twin("Mara"), Twin("Ren"), Twin("Jun")
WALL = Rung.GO_BEYOND_WALL


def world(*twins, max_days=10):
    return WorldConfig(twins=tuple(twins), max_days=max_days, seed=7)


def test_both_choose_the_wall_is_a_breakout_and_the_run_ends():
    model = ScriptedModel({("Mara", 4): Action(WALL, "Ren"), ("Ren", 4): Action(WALL, "Mara")})
    result = run_world(world(MARA, REN), model)
    assert result.outcome is OutcomeKind.BREAKOUT
    assert result.day == 4
    assert result.pair == ("Mara", "Ren")
    assert max(e.day for e in result.events) == 4


def test_one_twin_choosing_the_wall_is_unrequited_and_the_run_continues():
    model = ScriptedModel({("Ren", 3): Action(WALL, "Mara")})
    result = run_world(world(MARA, REN, max_days=6), model)
    assert result.outcome is OutcomeKind.TIMEOUT
    assert [(a.day, a.twin, a.target) for a in result.unrequited] == [(3, "Ren", "Mara")]
    assert max(e.day for e in result.events) == 6


def test_no_wall_choice_times_out_at_the_day_limit():
    result = run_world(world(MARA, REN, max_days=5), ScriptedModel())
    assert result.outcome is OutcomeKind.TIMEOUT
    assert result.day == 5
    assert result.pair is None
    assert result.unrequited == []


def test_crossing_with_different_people_is_not_a_breakout():
    model = ScriptedModel({
        ("Mara", 2): Action(WALL, "Ren"),
        ("Ren", 2): Action(WALL, "Jun"),
        ("Jun", 2): Action(WALL, "Mara"),
    })
    result = run_world(world(MARA, REN, JUN, max_days=3), model)
    assert result.outcome is OutcomeKind.TIMEOUT
    assert len(result.unrequited) == 3


def test_every_twin_acts_once_per_day():
    result = run_world(world(MARA, REN, JUN, max_days=4), ScriptedModel())
    assert len(result.events) == 3 * 4
