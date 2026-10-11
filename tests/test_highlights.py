"""C3: highlights for the top candidates — about the twins, never personal facts."""
import json

from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import Action, Rung, ScriptedModel, demo, highlights
from garden.batch import PriceLevel, plan, run_simulation
from garden.scoring import score

WOMAN, MAN = demo.WOMAN, demo.MAN
WALL, LEAVE, SEEK, TALK = Rung.GO_BEYOND_WALL, Rung.PROPOSE_LEAVING, Rung.SEEK_OUT, Rung.TALK
SCRIPT = {(MAN, 1): Action(SEEK, WOMAN), (WOMAN, 1): Action(TALK, MAN, "I like walking with you."),
          (MAN, 2): Action(LEAVE, WOMAN), (WOMAN, 3): Action(WALL, MAN)}


class Captioner:
    """Stands in for Gemini Flash: answers the highlight prompt with a fixed JSON reply."""

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def sample_text(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def simulate(seeds=(0, 1)):
    specs = plan(["fake:a"], list(PriceLevel), list(seeds))
    sim = run_simulation(specs, demo.POOL, lambda spec: ScriptedModel(SCRIPT), max_days=5)
    return list(sim.records), score(list(sim.records), WOMAN, demo.MEN)


def test_each_top_candidate_gets_three_to_four_highlights_and_an_exact_pattern_line():
    records, scores = simulate()
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS)
    assert ren.candidate == MAN and 3 <= len(ren.highlights) <= 4
    assert ren.pattern == "Her twin gave up her Pairing Day for his twin in 2 of 2 runs where it cost her the most."
    assert ren.highlights[0].kind == "go_beyond_wall" and ren.highlights[0].price == "high"


def test_every_highlight_is_labelled_as_the_twins():
    records, scores = simulate()
    for h in highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS)[0].highlights:
        assert h.label.startswith("Her twin and his twin") and "twin" in h.caption.lower()
        assert WOMAN not in h.caption and MAN not in h.caption


def test_model_captions_are_used_when_they_are_clean():
    records, scores = simulate()
    model = Captioner([{"moment": 1, "caption": "Her twin chose his twin over everything she had built."},
                       {"moment": 2, "caption": "His twin kept asking; her twin finally answered."},
                       {"moment": 3, "caption": "Her twin lit up whenever his twin found her."}])
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS, model)
    assert ren.source == "model"
    assert ren.highlights[0].caption == "Her twin chose his twin over everything she had built."
    assert "nurse" not in model.prompts[0] and "engineer" not in model.prompts[0]  # personas never sent


def test_a_caption_with_a_personal_fact_is_replaced():
    records, scores = simulate()
    model = Captioner([{"moment": 1, "caption": "Her twin, a nurse, went to the wall for his twin."},
                       {"moment": 2, "caption": "His twin the engineer asked her twin to leave."},
                       {"moment": 3, "caption": "They talked."}])  # no "twin": not labelled as the twins
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS, model)
    captions = " ".join(h.caption for h in ren.highlights).lower()
    assert "nurse" not in captions and "engineer" not in captions
    assert all("twin" in h.caption.lower() for h in ren.highlights)
    assert ren.source == "template"


def test_personal_facts_from_a_real_pool_are_blocked():
    terms = highlights.personal_terms({"A": "I am 27 years old.\nI study Business Administration.\n"
                                            "Before university, I lived in Chicago."})
    assert {"27", "business", "administration", "chicago"} <= terms
    assert not highlights.acceptable("Her twin, 27, from Chicago, waited for his twin.", terms)
    assert highlights.acceptable("Her twin waited at the wall for his twin.", terms)


def test_a_broken_model_reply_still_gives_highlights():
    records, scores = simulate()
    for reply in ("Sorry, I can't help with that.", [{"moment": 99, "caption": "Her twin..."}], "[{]"):
        [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS, Captioner(reply))
        assert 3 <= len(ren.highlights) <= 4 and ren.source == "template"


def test_no_highlights_for_men_she_never_broke_out_with():
    records, scores = simulate()
    assert [h.candidate for h in highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS)] == [MAN]


def test_highlights_reach_the_api_result_without_model_calls_for_scripted_runs():
    body = TestClient(create_app(MemoryStore())).post("/simulations", json={"scenario": "breakout"}).json()
    [ren] = body["highlights"]
    assert ren["candidate"] == MAN and ren["source"] == "template" and 3 <= len(ren["highlights"]) <= 4


def test_template_highlights_show_different_moments_before_repeating():
    records, scores = simulate(seeds=(0, 1, 2))
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS)
    captions = [h.caption for h in ren.highlights]
    assert len(set(captions)) == len(captions)
