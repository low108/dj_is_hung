"""B3: Longing and end-of-day reflections."""
import re

from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins, parse_reflection
from garden.engine_types import Situation
from garden.llm import CountingModel, KeywordModel
from garden.longing import Longing

MARA, REN, JUN = Twin("Mara"), Twin("Ren"), Twin("Jun")
TALK, REFLECT = Rung.TALK, Rung.REFLECT


def quiet(*names):
    return {n: Action(REFLECT) for n in names}


def test_longing_rises_while_apart_after_a_bond_and_falls_when_reunited():
    l = Longing()
    l.end_of_day({"Mara": Action(TALK, "Ren"), "Ren": Action(TALK, "Mara")})  # bond
    after_bond = l.of("Mara")["Ren"]
    for _ in range(3):
        l.end_of_day(quiet("Mara", "Ren"))  # apart
    apart = l.of("Mara")["Ren"]
    l.end_of_day({"Mara": Action(TALK, "Ren"), "Ren": Action(REFLECT)})  # together again
    reunited = l.of("Mara")["Ren"]
    assert apart > after_bond
    assert reunited < apart


def test_no_bond_means_no_longing():
    l = Longing()
    for _ in range(3):
        l.end_of_day(quiet("Mara", "Ren"))
    assert l.of("Mara") == {}
    assert l.describe("Mara") == ""


def test_longing_fades_without_new_bonding_eventually_stops_growing():
    l = Longing()
    l.end_of_day({"Mara": Action(TALK, "Ren")})
    levels = []
    for _ in range(40):
        l.end_of_day(quiet("Mara", "Ren"))
        levels.append(l.of("Mara")["Ren"])
    assert levels[-1] - levels[-2] < 0.01  # converges instead of growing forever


def test_twins_hear_longing_only_in_words():
    l = Longing()
    l.end_of_day({"Mara": Action(TALK, "Ren")})
    for _ in range(8):
        l.end_of_day(quiet("Mara", "Ren"))
    words = l.describe("Mara")
    assert "Ren" in words and not re.search(r"\d", words)


class Recording(ScriptedModel):
    def __init__(self, script):
        super().__init__(script)
        self.situations: list[tuple[str, int, Situation]] = []

    def choose_action(self, twin, day, others, situation=None):
        self.situations.append((twin.alias, day, situation))
        return super().choose_action(twin, day, others, situation)


def test_the_engine_passes_longing_to_the_model_and_reports_it():
    model = Recording({("Mara", 1): Action(TALK, "Ren"), **{("Mara", d): Action(REFLECT) for d in range(2, 7)},
                       **{("Ren", d): Action(REFLECT) for d in range(1, 7)}})
    result = run_world(WorldConfig((MARA, REN), max_days=6, seed=2), model)
    late = [s.longing for who, day, s in model.situations if who == "Mara" and day >= 5]
    assert any("Ren" in words for words in late)
    assert result.longing["Mara"]["Ren"] > 0


class PromptLog(KeywordModel):
    def __init__(self, say):
        super().__init__({}, say=say)
        self.prompts: list[str] = []

    def sample_text(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.say

    def sample_choice(self, prompt, responses, *, seed=None):
        self.prompts.append(prompt)
        return super().sample_choice(prompt, responses, seed=seed)


def test_reflections_are_written_daily_become_memories_and_ratings_stay_out():
    lm = PromptLog("I keep replaying today's talk by the fountain.\nRatings: longing=7; trust=4; standing_matters=6; on_my_mind=Ren")
    model = ConcordiaTwins(CountingModel(lm, letter_choices=False))
    result = run_world(WorldConfig((MARA, REN), max_days=3, seed=1), model)

    assert len(result.reflections) == 2 * 3
    first = result.reflections[0]
    assert first.text == "I keep replaying today's talk by the fountain."
    assert first.ratings == {"longing": 7, "trust": 4, "standing_matters": 6, "on_my_mind": "Ren"}

    day3_action_prompts = [p for p in lm.prompts if "do now on day 3" in p]
    assert day3_action_prompts and all("fountain" in p for p in day3_action_prompts)  # remembered
    assert not any("longing=7" in p for p in day3_action_prompts)  # ratings never fed back


def test_parse_reflection_handles_missing_ratings():
    text, ratings = parse_reflection("Mara", "Mara Today was quiet.")
    assert (text, ratings) == ("Today was quiet.", {})


def test_parse_reflection_strips_brackets_markdown_and_caps_length():
    raw = ("# Day 4\n\n*It was a long day.* I talked to Ren. I miss Mara. I wonder about Pairing Day. "
           "I could not sleep.\n---\nRatings: longing=<8>; trust=<3>; standing_matters=7; on_my_mind=Mara")
    text, ratings = parse_reflection("Sam", raw)
    assert text == "It was a long day. I talked to Ren. I miss Mara."
    assert ratings == {"longing": 8, "trust": 3, "standing_matters": 7, "on_my_mind": "Mara"}
