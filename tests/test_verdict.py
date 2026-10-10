"""B5: the verdict gate, through the run_world seam."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden import verdict as rules
from garden.concordia_twins import offered_options
from garden.engine_types import Situation
from garden.fake_model import CONTENT, RESTLESS
from garden.world_text import RUNG_OPTIONS

MARA, REN = Twin("Mara", "f"), Twin("Ren", "m")
WALL, LEAVE = Rung.GO_BEYOND_WALL, Rung.PROPOSE_LEAVING
BOTH_TRY_THE_WALL = {(who, d): Action(WALL, other) for who, other in (("Mara", "Ren"), ("Ren", "Mara"))
                     for d in range(1, 6)}


def run(ratings, days=5, **config):
    model = ScriptedModel(BOTH_TRY_THE_WALL, ratings=ratings)
    return run_world(WorldConfig((MARA, REN), max_days=days, seed=1, **config), model)


def test_pressure_from_ratings():
    assert rules.pressure(RESTLESS) > 0.9  # ratings are 1-10, so the extremes are 0.94 / 0.04
    assert rules.pressure(CONTENT) < 0.1
    assert rules.pressure({}) is None


def test_with_the_gate_closed_no_one_proposes_or_crosses_even_if_the_model_tries():
    result = run(CONTENT)
    assert not [e for e in result.events if e.rung in rules.GATED_RUNGS]
    assert result.outcome is OutcomeKind.TIMEOUT
    assert all(not v.permitted for v in result.verdicts)


def test_day_one_is_closed_because_no_one_has_reflected_yet():
    result = run(RESTLESS, days=1)
    assert all(not v.permitted and v.score is None for v in result.verdicts)
    assert result.outcome is OutcomeKind.TIMEOUT


def test_once_permitted_the_choice_is_the_models():
    result = run(RESTLESS)
    assert result.outcome is OutcomeKind.BREAKOUT and result.day == 2


def test_the_threshold_decides_for_the_same_feelings():
    mid = {"longing": 8, "trust": 4, "standing_matters": 5}  # pressure 0.65
    assert rules.pressure(mid) == 0.65
    assert run(mid, thresholds=(("Mara", 0.6), ("Ren", 0.6))).outcome is OutcomeKind.BREAKOUT
    assert run(mid, thresholds=(("Mara", 0.7), ("Ren", 0.7))).outcome is OutcomeKind.TIMEOUT


def test_the_gate_can_be_switched_off_for_the_ablation():
    result = run(CONTENT, gate_enabled=False)
    assert result.outcome is OutcomeKind.BREAKOUT and result.day == 1


def test_every_verdict_is_logged_per_twin_per_day():
    result = run(CONTENT, days=3)
    assert {(v.day, v.twin) for v in result.verdicts} == {(d, t) for d in (1, 2, 3) for t in ("Mara", "Ren")}


def test_a_permitted_gate_only_adds_the_two_options_and_no_other_wording():
    closed, opened = offered_options(Situation(may_break_rules=False)), offered_options(Situation(may_break_rules=True))
    assert set(opened) - set(closed) == {RUNG_OPTIONS["propose_leaving"], RUNG_OPTIONS["go_beyond_wall"]}
    assert set(closed) <= set(opened)


def test_a_noticed_proposal_becomes_a_logged_rumour():
    model = ScriptedModel({("Ren", d): Action(LEAVE, "Mara") for d in range(2, 10)})
    result = run_world(WorldConfig((MARA, REN), max_days=9, seed=3), model)
    rumours = [a for a in result.announcements if "whisper" in a.text]
    proposals = [e for e in result.events if e.rung is LEAVE]
    assert proposals and 0 < len(rumours) <= len(proposals)  # "may be noticed": some, not always
