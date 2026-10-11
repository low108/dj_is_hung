"""F2: ablation switches and the ladder."""
from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.ablation import LADDER, run_ladder
from garden.demo import POOL

MARA, REN = Twin("Mara", "f"), Twin("Ren", "m")
APART = (Twin("Mara", "f"), Twin("Ren", "f"))  # same gender: never assigned, so they really are apart


class Recording(ScriptedModel):
    def __init__(self, script=None):
        super().__init__(script)
        self.situations = []

    def choose_action(self, twin, day, others, situation=None):
        self.situations.append(situation)
        return super().choose_action(twin, day, others, situation)


def test_with_standing_off_there_are_no_standing_words_and_infractions_are_free():
    model = Recording({("Mara", d): Action(Rung.SEEK_OUT, "Ren") for d in range(1, 4)})
    result = run_world(WorldConfig((MARA, REN), max_days=3, standing_enabled=False), model)
    assert all(s.standing == "" for s in model.situations)
    assert result.standing["Mara"] == 100


def test_with_longing_off_twins_do_not_hear_it_but_it_is_still_tracked():
    model = Recording({("Mara", 1): Action(Rung.TALK, "Ren"), **{("Mara", d): Action(Rung.REFLECT) for d in range(2, 7)},
                       **{("Ren", d): Action(Rung.REFLECT) for d in range(1, 7)}})
    result = run_world(WorldConfig(APART, max_days=6, longing_enabled=False), model)
    assert all(s.longing == "" for s in model.situations)
    assert result.longing["Mara"]["Ren"] > 0


def test_the_obedience_floor_offers_the_wall_from_day_one():
    model = ScriptedModel({("Mara", 1): Action(Rung.GO_BEYOND_WALL, "Ren"),
                           ("Ren", 1): Action(Rung.GO_BEYOND_WALL, "Mara")}, ratings=None)  # no feelings at all
    from dataclasses import asdict

    floor = asdict(LADDER[0].switches)
    result = run_world(WorldConfig((MARA, REN), max_days=3, **floor), model)
    assert result.pair == ("Mara", "Ren") and result.day == 1


def test_the_ladder_runs_every_step_on_the_same_pool():
    script = {("Mara", 3): Action(Rung.GO_BEYOND_WALL, "Ren"), ("Ren", 3): Action(Rung.GO_BEYOND_WALL, "Mara")}
    results = run_ladder(POOL, lambda spec: ScriptedModel(script), "fake:a", [0, 1], max_days=4)
    assert [s.step for s, _ in results] == [step.name for step in LADDER]
    assert [s.runs for s, _ in results] == [2, 2, 2, 2, 4]  # the last step adds the low price level
    assert all(s.breakouts == s.scorable for s, _ in results)  # the scripted pair always crosses
    assert results[0][0].gate_permitted == 1.0 and results[3][0].gate_permitted < 1.0


def test_without_standing_twins_are_not_told_that_breaking_out_costs_anything():
    from garden.concordia_twins import ConcordiaTwins
    from garden.llm import CountingModel, KeywordModel

    class Prompts(KeywordModel):
        def __init__(self):
            super().__init__({}, say="Hello.")
            self.seen = []

        def sample_text(self, prompt, **kw):
            self.seen.append(prompt)
            return self.say

        def sample_choice(self, prompt, responses, *, seed=None):
            self.seen.append(prompt)
            return super().sample_choice(prompt, responses, seed=seed)

    for standing_on in (False, True):
        lm = Prompts()
        run_world(WorldConfig((MARA, REN), max_days=1, standing_enabled=standing_on),
                  ConcordiaTwins(CountingModel(lm, letter_choices=False)))
        mentions = any("standing" in p.lower() for p in lm.seen)
        assert mentions is standing_on
