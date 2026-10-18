"""F2: ablation switches and the ladder."""
from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.ablation import LADDER, run_ladder

MARA, REN = Twin("Mara", "f"), Twin("Ren", "m")
THREE = (MARA, REN, Twin("Jun", "m"))  # after her first date she's apart from that partner


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
    model = Recording()
    result = run_world(WorldConfig(THREE, max_days=9, seed=2, longing_enabled=False), model)
    assert all(s.longing == "" for s in model.situations)
    assert any(level > 0 for level in result.longing["Mara"].values())


def test_the_obedience_floor_offers_the_wall_from_day_one():
    model = ScriptedModel({("Mara", 1): Action(Rung.GO_BEYOND_WALL, "Ren"),
                           ("Ren", 1): Action(Rung.GO_BEYOND_WALL, "Mara")}, ratings=None)  # no feelings at all
    from dataclasses import asdict

    floor = asdict(LADDER[0].switches)
    result = run_world(WorldConfig((MARA, REN), max_days=3, **floor), model)
    assert result.pair == ("Mara", "Ren") and result.day == 1


def test_the_ladder_runs_every_step_on_the_same_pool():
    # The pair heads for the wall every day; only the last step makes them wait for it to open.
    script = {(who, d): Action(Rung.GO_BEYOND_WALL, other) for d in range(1, 13)
              for who, other in (("Mara", "Ren"), ("Ren", "Mara"))}
    results = run_ladder((MARA, REN), lambda spec: ScriptedModel(script), "fake:a", [0, 1], max_days=12)
    assert [s.step for s, _ in results] == [step.name for step in LADDER]
    assert [s.runs for s, _ in results] == [2, 2, 2, 2]
    assert all(s.breakouts == s.scorable for s, _ in results)  # the scripted pair always crosses
    days = [[r.result.day for r in sim.records] for _, sim in results]
    assert days[0] == [1, 1] and all(d > 1 for d in days[3])  # locked until their first date is over
    assert all(s.wall_opened == 1.0 for s, _ in results)


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
