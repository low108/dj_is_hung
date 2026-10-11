"""C3: highlights for the top candidates — about the twins, never personal facts."""
import json

from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import Action, Rung, demo, highlights
from garden.fake_model import ScenarioModel
from garden.batch import plan, run_simulation
from garden.scoring import score

WOMAN, MAN = demo.WOMAN, demo.MAN
WALL, LEAVE, SEEK, TALK = Rung.GO_BEYOND_WALL, Rung.PROPOSE_LEAVING, Rung.SEEK_OUT, Rung.TALK


def breakout(spec=None):
    """When Mara and Ren meet: she talks, he proposes leaving, she answers at the wall."""
    return ScenarioModel("breakout", WOMAN, MAN)


class Captioner:
    """Stands in for Gemini Flash: answers the highlight prompt with a fixed JSON reply."""

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def sample_text(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def simulate(seeds=(0, 1)):
    specs = plan(["fake:a"], list(seeds))
    sim = run_simulation(specs, demo.POOL, breakout)
    return list(sim.records), score(list(sim.records), WOMAN, demo.MEN)


def test_each_top_candidate_gets_three_to_four_highlights_and_an_exact_pattern_line():
    records, scores = simulate()
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS)
    assert ren.candidate == MAN and 3 <= len(ren.highlights) <= 4
    assert ren.pattern == ("Her twin tried to leave the Garden with his twin in 2 of the 2 runs where they had a date. "
                           "They crossed together in 2.")
    assert [h.kind for h in ren.highlights[:2]] == ["breakout", "go_beyond_wall"]


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


def test_highlights_reach_the_api_result_without_model_calls_for_scripted_runs(monkeypatch):
    monkeypatch.setenv("HIGHLIGHT_MODEL", "gemini:would-cost-money")  # ignored: scripted runs never call a model
    body = TestClient(create_app(MemoryStore())).post("/simulations", json={"scenario": "breakout"}).json()
    [ren] = body["highlights"]
    assert ren["candidate"] == MAN and ren["source"] == "template" and 3 <= len(ren["highlights"]) <= 4
    assert len({h["caption"] for h in ren["highlights"]}) == len(ren["highlights"])


def test_three_letter_and_inflected_persona_facts_are_blocked():
    terms = highlights.personal_terms({"A": "I study law.\nI am a nurse.\nBefore university, I lived in NYC."})
    for caption in ("Her twin, a law student, waited for his twin.", "Her twin left nursing behind for his twin.",
                    "Her twin missed NYC less with his twin."):
        assert not highlights.acceptable(caption, terms), caption
    assert highlights.acceptable("Her twin waited at the wall for his twin, and he came.", terms)


def test_the_model_never_sees_what_the_twins_said():
    class Chatty(ScenarioModel):
        def choose_action(self, twin, day, others, situation=None):
            action = super().choose_action(twin, day, others, situation)
            if action.say:
                return Action(action.rung, action.target, "As a nurse in Chicago I rarely get evenings off.")
            return action

    specs = plan(["fake:a"], [0])
    sim = run_simulation(specs, demo.POOL, lambda spec: Chatty("breakout", WOMAN, MAN))
    records = list(sim.records)
    model = Captioner([])
    highlights.for_simulation(records, score(records, WOMAN, demo.MEN), WOMAN, demo.PERSONAS, model)
    assert "Chicago" not in model.prompts[0] and "nurse" not in model.prompts[0]


def test_a_rejected_caption_never_repeats_a_template():
    records, scores = simulate()
    model = Captioner([{"moment": 1, "caption": "the nurse"}, {"moment": 1, "caption": "again"},
                       {"moment": True, "caption": "Her twin, moment True."}])
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS, model)
    captions = [h.caption for h in ren.highlights]
    assert len(set(captions)) == len(captions) and 3 <= len(captions) <= 4


def test_template_highlights_show_different_moments_before_repeating():
    records, scores = simulate(seeds=(0, 1, 2))
    [ren] = highlights.for_simulation(records, scores, WOMAN, demo.PERSONAS)
    captions = [h.caption for h in ren.highlights]
    assert len(set(captions)) == len(captions)
