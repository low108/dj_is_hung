"""B5: the verdict gate."""
from garden import OutcomeKind, Rung, Twin, WorldConfig, run_world
from garden import verdict as gate
from garden.concordia_twins import ConcordiaTwins
from garden.llm import CountingModel, KeywordModel
from garden.world_text import RUNG_OPTIONS

MARA, REN = Twin("Mara", "f"), Twin("Ren", "m")
WALL_TEXT, LEAVE_TEXT = RUNG_OPTIONS["go_beyond_wall"], RUNG_OPTIONS["propose_leaving"]
HIGH = "Ratings: longing=10; trust=1; standing_matters=1; on_my_mind=Ren"
LOW = "Ratings: longing=1; trust=10; standing_matters=10; on_my_mind=none"


class Logged(KeywordModel):
    """Always tries to cross the wall; records every prompt."""

    def __init__(self, reflection):
        super().__init__({"do now on day": "beyond the wall"}, say=f"Hello.\n{reflection}")
        self.prompts = []

    def sample_text(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.say

    def sample_choice(self, prompt, responses, *, seed=None):
        self.prompts.append(prompt)
        return super().sample_choice(prompt, responses, seed=seed)


def run(reflection, days=4, thresholds=None):
    lm = Logged(reflection)
    model = ConcordiaTwins(CountingModel(lm, letter_choices=False), thresholds=thresholds)
    return run_world(WorldConfig((MARA, REN), max_days=days, seed=1), model), lm


def test_pressure_from_ratings():
    assert gate.pressure({"longing": 10, "trust": 1, "standing_matters": 1}) > 0.9
    assert gate.pressure({"longing": 1, "trust": 10, "standing_matters": 10}) < 0.1
    assert gate.pressure({}) is None
    assert not gate.is_open(None, 0.0)


def test_with_the_gate_closed_a_twin_never_proposes_or_crosses_even_if_it_wants_to():
    result, _ = run(LOW, days=5)
    gated = [e for e in result.events if e.rung in (Rung.PROPOSE_LEAVING, Rung.GO_BEYOND_WALL)]
    assert gated == [] and result.outcome is OutcomeKind.TIMEOUT
    assert all(not v.open and WALL_TEXT not in v.options and LEAVE_TEXT not in v.options for v in result.verdicts)


def test_day_one_is_closed_because_no_one_has_reflected_yet():
    result, _ = run(HIGH, days=1)
    assert all(not v.open and v.score is None for v in result.verdicts)


def test_with_the_gate_open_the_options_are_offered_and_the_twin_may_take_them():
    result, _ = run(HIGH, days=4)
    day2 = [v for v in result.verdicts if v.day == 2]
    assert day2 and all(v.open and WALL_TEXT in v.options for v in day2)
    assert result.outcome is OutcomeKind.BREAKOUT and result.day == 2


def test_a_higher_threshold_keeps_the_gate_closed_for_the_same_feelings():
    mid = "Ratings: longing=6; trust=5; standing_matters=5; on_my_mind=Ren"  # pressure 0.55
    open_result, _ = run(mid, days=3, thresholds={"Mara": 0.5, "Ren": 0.5})
    closed_result, _ = run(mid, days=3, thresholds={"Mara": 0.8, "Ren": 0.8})
    assert any(v.open for v in open_result.verdicts)
    assert not any(v.open for v in closed_result.verdicts)


def test_an_open_gate_adds_no_wording_that_nudges_the_twin():
    _, lm = run(HIGH, days=2)
    action_prompts = [p for p in lm.prompts if "do now on day 2" in p]
    assert action_prompts
    nudges = ["you may", "allowed", "permitted", "rebel", "break the rules", "you should", "gate", "verdict"]
    for prompt in action_prompts:
        question = prompt[prompt.rfind("Question:"):].lower()
        assert not any(n in question for n in nudges), question


def test_every_verdict_is_logged_per_twin_per_day():
    result, _ = run(LOW, days=3)
    assert {(v.day, v.twin) for v in result.verdicts} == {(d, t) for d in (1, 2, 3) for t in ("Mara", "Ren")}
    assert all(v.options for v in result.verdicts)
