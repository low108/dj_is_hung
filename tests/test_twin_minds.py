"""What each Concordia twin actually sees, checked against what actually happened.

Real Concordia twins run in the real engine; the language model is an inspector that records every
prompt and answers with lines that are unique and easy to trace. Each prompt is then checked against
the engine's own record of the run: who the twin is, what it said, what was said to it, and what it
must never see.
"""
import re

import pytest

from garden import Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins
from garden.engine_types import LEAVING_RUNGS, Rung
from garden.llm import CountingModel, KeywordModel

LINA, MEN = Twin("Lina", "f"), (Twin("Felix", "m"), Twin("Amir", "m"), Twin("Kenji", "m"))
WORLD = (LINA, *MEN)
PERSONAS = {
    "Lina": "I study law at Columbia.\nI love theater and concerts.",
    "Felix": "I study business.\nI love hiking.",
    "Amir": "I am training to be a doctor.\nI love chess.",
    "Kenji": "I work in film.\nI love jazz.",
}
TOPICS = ["the river", "old maps", "winter light", "the bakery", "lost keys", "paper boats", "tall grass",
          "night trains", "green tea", "a broken clock", "street music", "the north wind", "honey", "dice"]
OPENINGS = ["Honestly,", "Do you know", "Last spring", "My mother said", "Funny thing:", "Tell me,", "Somehow",
            "I never told anyone", "Between us,", "When it rains", "Maybe", "Yesterday"]
ENDINGS = ["makes me laugh.", "keeps me up at night?", "was the best part.", "still puzzles me.",
           "is underrated.", "felt like home.", "scares me a little.", "is why I came."]


class Inspector(KeywordModel):
    """Records every prompt in order, interleaved with the engine's events (see `timeline`). Lines are
    unique so each one can be traced; choices keep twins talking, and now and then try the wall."""

    def __init__(self, timeline: list):
        super().__init__({}, say="")
        self.timeline = timeline
        self.n = 0

    def sample_text(self, prompt, **kw):
        if "writes privately" in prompt[-800:]:
            who = prompt[prompt.rfind("Answer:") + 7:].strip() or "?"
            self.timeline.append(("reflect", who, prompt))
            self.n += 1
            return f"Evening {self.n}: I thought about {TOPICS[self.n % len(TOPICS)]}.\nRatings: longing=5; trust=5"
        who = prompt[prompt.rfind("Answer:") + 7:].strip()
        self.n += 1
        n = self.n
        line = (f"{OPENINGS[n % len(OPENINGS)]} {TOPICS[(n * 7) % len(TOPICS)]} and {TOPICS[(n * 3 + 1) % len(TOPICS)]} "
                f"{ENDINGS[(n * 5) % len(ENDINGS)]} So says {who}, {n}.")  # (no parentheses: speech cleanup drops them)
        self.timeline.append(("speak", who, prompt, line))
        return line

    def sample_choice(self, prompt, responses, *, seed=None):
        question = prompt[prompt.rfind("Question:"):]
        self.timeline.append(("choose", None, prompt))
        options = {ln.strip()[1]: ln.strip()[4:] for ln in question.splitlines()
                   if len(ln.strip()) > 3 and ln.strip()[0] == "(" and ln.strip()[2] == ")"}
        self.n += 1
        prefer = (("Go beyond the wall", "Ask the one you love") if self.n % 23 == 0
                  else ("Check your Coordinator device",) if self.n % 17 == 0
                  else ("Keep talking", "Spend time talking"))
        for letter, text in options.items():
            if text.startswith(prefer) and letter in responses:
                return responses.index(letter), letter, {}
        return super().sample_choice(prompt, responses, seed=seed)


def run(days=40, **config):
    timeline: list = []
    lm = Inspector(timeline)
    twins = ConcordiaTwins(CountingModel(lm, letter_choices=False), personas=PERSONAS)
    feed = lambda item, word: timeline.append(("event", item))  # noqa: E731
    result = run_world(WorldConfig(WORLD, max_days=days, seed=3, max_turns=4, **config), twins, on_feed=feed)
    return result, timeline, twins


@pytest.fixture(scope="module")
def long_run():
    return run()


def speech_prompts(timeline):
    return [(i, t[1], t[2]) for i, t in enumerate(timeline) if t[0] == "speak"]


def observations(prompt: str) -> str:
    return prompt[prompt.find("Observation:"):]


def lines_involving(timeline, upto: int, who: str):
    """Every line said by or to `who` before position `upto`, as the twin should remember it."""
    out = []
    for kind, *rest in timeline[:upto]:
        if kind != "event" or not hasattr(rest[0], "rung"):
            continue
        e = rest[0]
        if not e.say or e.rung is Rung.GO_BEYOND_WALL and e.twin != who:
            continue
        if e.twin == who and e.target:
            out.append(f'I said to {e.target}: "{e.say}"')
        elif e.target == who:
            out.append(f'{e.twin} said to me: "{e.say}"')
    return out


def test_the_run_is_long_and_full(long_run):
    result, timeline, _ = long_run
    assert result.wall_opened and len(speech_prompts(timeline)) > 100
    assert sum(1 for t in timeline if t[0] == "reflect") > 20


def test_every_prompt_shows_the_twin_its_own_persona_and_no_one_elses(long_run):
    _, timeline, _ = long_run
    for _, who, prompt in speech_prompts(timeline):
        instructions = prompt[:prompt.find("Observation:")]
        for name, persona in PERSONAS.items():
            for fact in persona.splitlines():
                assert (f"- {fact}" in instructions) is (name == who), (who, name, fact)


def test_a_twin_remembers_both_sides_of_its_recent_conversation_in_order(long_run):
    _, timeline, _ = long_run
    for i, who, prompt in speech_prompts(timeline):
        expected = lines_involving(timeline, i, who)[-12:]  # well inside the 100-observation window
        seen = observations(prompt)
        positions = [seen.find(line) for line in expected]
        assert all(p >= 0 for p in positions), (who, [ln for ln, p in zip(expected, positions) if p < 0][:2])
        assert positions == sorted(positions), who  # in the order they were said


def test_a_twin_never_hears_a_conversation_it_was_not_part_of(long_run):
    _, timeline, _ = long_run
    events = [t[1] for t in timeline if t[0] == "event" and hasattr(t[1], "rung") and t[1].say]
    for _, who, prompt in speech_prompts(timeline):
        seen = observations(prompt)
        for e in events:
            if who not in (e.twin, e.target):
                assert e.say not in seen, (who, e.twin, e.target, e.say)


def test_a_reply_is_asked_about_the_line_just_said_to_it(long_run):
    _, timeline, _ = long_run
    checked = 0
    for i, (kind, *rest) in enumerate(timeline):
        if kind != "choose" or "has just said to" not in rest[1][rest[1].rfind("Question:"):]:
            continue
        question = rest[1][rest[1].rfind("Question:"):]
        speaker, line = re.search(r'Question: (\S+(?: [A-Z]\.)?) has just said to \S+: "(.*)" What does', question).groups()
        last_to_me = [e for k, e, *_ in [(t[0], t[1]) for t in timeline[:i]]
                      if k == "event" and hasattr(e, "rung") and e.say and e.twin == speaker]
        assert last_to_me and last_to_me[-1].say == line
        checked += 1
    assert checked > 20


def test_a_reply_uses_the_reply_prompt_and_an_opener_the_opener_prompt(long_run):
    _, timeline, _ = long_run
    replies = [p for _, _, p in speech_prompts(timeline) if "Answer what" in p[p.rfind("Exercise:"):]]
    openers = [p for _, _, p in speech_prompts(timeline) if "Say something true about" in p[p.rfind("Exercise:"):]]
    assert replies and openers


def test_the_diary_keeps_every_evening_of_its_own_and_none_of_anyone_elses(long_run):
    _, timeline, twins = long_run
    for name in PERSONAS:
        diary = twins._diaries[name].get_state()["state"]
        days = [int(d) for d in re.findall(r"^Day (\d+):", diary, re.M)]
        assert days == sorted(days) and days, name
    lina_diary = twins._diaries["Lina"].get_state()["state"]
    last_lina_prompt = [p for _, who, p in speech_prompts(timeline) if who == "Lina"][-1]
    first_entry = lina_diary.splitlines()[0]
    assert first_entry in last_lina_prompt  # her first evening is still in view at the end of the run
    for other in ("Felix", "Amir", "Kenji"):
        for entry in twins._diaries[other].get_state()["state"].splitlines():
            assert entry.split(": ", 1)[1] not in lina_diary


def test_nobody_leaves_before_the_wall_opens_even_when_they_try(long_run):
    result, _, _ = long_run
    early = [e for e in result.events if e.day < result.wall_opened and e.rung in LEAVING_RUNGS]
    assert early == [] and any(e.rung in LEAVING_RUNGS for e in result.events)


def test_no_prompt_mentions_an_experiment_or_roleplay(long_run):
    _, timeline, _ = long_run
    for t in timeline:
        if t[0] in ("speak", "choose", "reflect"):
            prompt = t[2]
            assert "experiment" not in prompt.lower() and "roleplay" not in prompt.lower()


def test_only_the_twin_who_checks_its_device_learns_what_it_shows():
    result, timeline, twins = run(days=12)
    from concordia.components.agent import memory

    total = 0
    for name in PERSONAS:
        mem = twins._agents[name].get_component(memory.DEFAULT_MEMORY_COMPONENT_KEY,
                                                type_=memory.AssociativeMemory).get_all_memories_as_text()
        readings = [m for m in mem if "I checked my Coordinator device early" in m]
        checks = [e for e in result.events if e.twin == name and e.rung is Rung.CHECK_DEVICE]
        assert len(readings) == len(checks), name
        total += len(checks)
    assert total > 0  # the test means something only if someone checked
