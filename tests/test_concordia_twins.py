"""Seam 1 through real Concordia agents, with an offline scripted language model."""
from garden import OutcomeKind, Rung, Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins
from garden.llm import CountingModel, KeywordModel

MARA, REN = Twin("Mara"), Twin("Ren")


# Speech uses the first line; the evening reflection uses the whole text (its ratings are only logged).
OPEN_GATE = "Come with me.\nRatings: longing=10; trust=1; standing_matters=1; on_my_mind=someone"


def twins(picks):
    lm = CountingModel(KeywordModel(picks, say=OPEN_GATE), letter_choices=False)
    return ConcordiaTwins(lm), lm


def test_concordia_twins_can_break_out_together():
    model, lm = twins({
        "Mara do now on day 3": "beyond the wall",
        "Ren do now on day 3": "beyond the wall",
    })
    result = run_world(WorldConfig((MARA, REN), max_days=5, seed=1, wall_lock=False), model)
    assert result.outcome is OutcomeKind.BREAKOUT
    assert result.day == 3
    assert result.pair == ("Mara", "Ren")
    wall = [e for e in result.events if e.rung is Rung.GO_BEYOND_WALL]
    assert {(e.twin, e.target) for e in wall} == {("Mara", "Ren"), ("Ren", "Mara")}
    assert lm.stats.choice_calls >= 6  # one rung choice per twin per day


def test_concordia_twins_one_sided_wall_is_unrequited():
    model, _ = twins({"Ren do now on day 2": "beyond the wall"})
    result = run_world(WorldConfig((MARA, REN), max_days=3, seed=1, wall_lock=False), model)
    assert result.outcome is OutcomeKind.TIMEOUT
    assert [(a.twin, a.target) for a in result.unrequited] == [("Ren", "Mara")]


def test_social_actions_carry_speech_and_reach_the_other_twin():
    model, _ = twins({"Ren do now on day 1": "talking"})
    result = run_world(WorldConfig((MARA, REN), max_days=1, seed=1), model)
    talk = [e for e in result.events if e.rung is Rung.TALK and e.twin == "Ren"]
    assert talk and talk[0].say == "Come with me." and talk[0].target == "Mara"
