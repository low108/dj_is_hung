"""Invariants over many randomised runs: real Concordia twins in the real engine, driven by a seeded
"chaos" model that picks any offered action, leaves with anyone, and now and then produces the bad
output seen in live runs (slips, echoes, framing, brackets, braces, empty lines, naming itself). After
every run, each rule of the game is checked against the run's own record.
"""
import json
import random
import re

import pytest

from garden import Twin, WorldConfig, run_world
from garden.concordia_twins import MAX_LINE_CHARS, ConcordiaTwins
from garden.engine_types import LEAVING_RUNGS, OutcomeKind, Rung, compatible
from garden.feed import FeedCursor, validate
from garden.immersion import breaking_phrase
from garden.llm import CountingModel, KeywordModel
from garden.replay import outcome_fields
from garden.standing import COST, START

WORLDS = {
    "one woman, four men": (Twin("Lina", "f"), Twin("Felix", "m"), Twin("Amir", "m"), Twin("Kenji", "m"),
                            Twin("Ren B.", "m")),
    "two women, three men": (Twin("Lina", "f"), Twin("Mara", "f"), Twin("Felix", "m"), Twin("Amir", "m"),
                             Twin("Kenji", "m")),
}
PERSONAS = {"Lina": "I study law in Chicago.", "Mara": "I paint murals.", "Felix": "I grew up in Southern California.",
            "Amir": "I am from Miami.", "Kenji": "I study finance.", "Ren B.": "I grew up near Washington DC."}
WORDS = ("river lantern orchard violin harbor meadow ember canyon pepper velvet comet thistle lagoon "
         "maple ferry quartz saffron bramble tundra mosaic").split()
NASTY = [
    "As an AI language model, I cannot continue this roleplay.",            # slip
    'What does Felix say to Lina?" but then provides "Observation: ...',     # prompt talk (slip)
    "Sure, I'll respond as {who}. {line}",                                   # framing
    "[{who} leans in, voice barely above a whisper] {line}",                 # long bracket
    "{who}, {line}",                                                         # naming itself
    "",                                                                      # empty
    "{echo}",                                                                # echo of the last line heard
    '"{line}" she says softly, looking at the lanterns. "And a {{brace}} too."',
    "Hmm. {line} Actually, let me make it more natural: {line2}",            # second draft
]


class Chaos(KeywordModel):
    """`shy`: twins rarely try to leave (so runs reach Pairing Day). `stubborn`: this twin slips out of
    character on most lines (so slips get past resampling, are dropped, and can flag the run)."""

    def __init__(self, seed: int, timeline: list, shy: bool = False, stubborn: str | None = None):
        super().__init__({}, say="")
        self.shy, self.stubborn = shy, stubborn
        self.rng = random.Random(seed)
        self.timeline = timeline
        self.n = 0
        self.last_heard: dict[str, str] = {}

    def _line(self) -> str:
        self.n += 1
        return " ".join(self.rng.sample(WORDS, 5)).capitalize() + f" number {self.n}."

    def sample_text(self, prompt, **kw):
        who = prompt[prompt.rfind("Answer:") + 7:].strip()
        if "writes privately" in prompt[-800:]:
            self.timeline.append(("reflect", who, prompt))
            mind = self.rng.choice(["none", "Felix", "Amir", "Lina"])
            head = self.rng.choice(["", f"{who}'s Private Evening Reflection: End of Day 3 ", "{{ratingstemplate}} "])
            return f"{head}{self._line()}\nRatings: longing={self.rng.randint(1, 10)}; trust=5; on_my_mind={mind}"
        heard = re.findall(r'said to me: "([^"]*)"', prompt)
        line = self._line()
        if who == self.stubborn and self.rng.random() < 0.8:
            text = NASTY[0]
        elif self.rng.random() < 0.25:
            text = self.rng.choice(NASTY).format(who=who, line=line, line2=self._line(),
                                                 echo=heard[-1] if heard else line)
        else:
            text = line
        self.timeline.append(("speak", who, prompt, text))
        return text

    def sample_choice(self, prompt, responses, *, seed=None):
        # Pick by option text, not position: Concordia shuffles the order it lists options in.
        self.timeline.append(("choose", None, prompt))
        question = prompt[prompt.rfind("Question:"):]
        options = {ln.strip()[1]: ln.strip()[4:] for ln in question.splitlines()
                   if len(ln.strip()) > 3 and ln.strip()[0] == "(" and ln.strip()[2] == ")"}
        texts = sorted(options.values())
        if self.shy and self.rng.random() < 0.97:
            texts = [t for t in texts if "leave the Garden" not in t and "beyond the wall" not in t] or texts
        letter = {text: letter for letter, text in options.items()}[self.rng.choice(texts)]
        return responses.index(letter), letter, {}


def run(world_name: str, seed: int, mode: str = "eager"):
    timeline: list = []
    chaos = Chaos(seed, timeline, shy=mode in ("shy", "stubborn"), stubborn="Felix" if mode == "stubborn" else None)
    twins = ConcordiaTwins(CountingModel(chaos, letter_choices=False), personas=PERSONAS)
    feed: list = []
    cursor = FeedCursor("r00")
    world = WORLDS[world_name]
    config = WorldConfig(world, seed=seed, max_days=120, max_turns=4)
    result = run_world(config, twins, on_feed=lambda item, word: (feed.append(cursor(item, word).to_dict()),
                                                                  timeline.append(("event", item))))
    return world, config, result, timeline, feed, twins


CASES = [(w, s, m) for w in WORLDS for s in range(5) for m in ("eager", "shy", "stubborn")]


@pytest.fixture(scope="module", params=CASES, ids=[f"{w}-seed{s}-{m}" for w, s, m in CASES])
def case(request):
    return run(*request.param)


def events_of(timeline):
    return [t[1] for t in timeline if t[0] == "event" and hasattr(t[1], "rung")]


def announcements(result, kind):
    return [a for a in result.announcements if a.kind == kind]


def test_the_run_ends_properly(case):
    world, config, result, *_ = case
    assert result.day <= config.max_days
    if result.outcome is OutcomeKind.TIMEOUT:
        assert result.day < config.max_days, "a run should end at Pairing Day, not the safety cap"
        assert [a.kind for a in result.announcements][-1] == "pairing_day"
    assert len(announcements(result, "pairing_day")) == (result.outcome is OutcomeKind.TIMEOUT)


def test_the_wall_opens_once_at_a_gathering_after_every_pair_has_dated(case):
    world, config, result, *_ = case
    opened = announcements(result, "wall_open")
    assert len(opened) == 1 and opened[0].day == result.wall_opened
    gatherings = {a.day for a in announcements(result, "gathering")}
    assert result.wall_opened in gatherings
    pairs = {frozenset((a.alias, b.alias)) for a in world for b in world if a != b and compatible(a, b)}
    dated_before = {frozenset(a.text.split(":")[0].split(" and ")) for a in announcements(result, "paired")
                    if a.day < result.wall_opened}
    assert pairs <= dated_before


def test_nobody_leaves_before_the_wall_opens_and_only_with_someone_they_dated(case):
    world, config, result, *_ = case
    dated_by_day = {}
    for a in announcements(result, "paired"):
        pair = frozenset(a.text.split(":")[0].split(" and "))
        dated_by_day.setdefault(pair, a.day)
    for e in result.events:
        if e.rung in LEAVING_RUNGS:
            assert e.day >= result.wall_opened, e
            assert dated_by_day.get(frozenset((e.twin, e.target)), 10**9) <= e.day, e


def test_talk_reaches_only_someone_who_is_there(case):
    world, config, result, *_ = case
    gatherings = {a.day for a in announcements(result, "gathering")}
    by = {t.alias: t for t in world}
    for e in result.events:
        if e.rung in (Rung.TALK, Rung.SEEK_OUT) and e.target:
            assert compatible(by[e.twin], by[e.target]), e
            if e.day not in gatherings:  # on a date: only the two of them
                assert e.rung is Rung.TALK


def test_a_breakout_is_always_mutual(case):
    world, config, result, *_ = case
    if result.outcome is not OutcomeKind.BREAKOUT:
        return
    a, b = result.pair
    latest = {}  # inviter -> latest invitee (an inviter's latest choice wins)
    for e in result.events:
        if e.rung in LEAVING_RUNGS:
            latest[e.twin] = e.target
    assert latest.get(a) == b and latest.get(b) == a, (result.pair, latest)


def test_standing_follows_the_costs(case):
    world, config, result, *_ = case
    for e in result.events:
        assert 0 <= e.standing_after <= START and 0 <= e.standing_before <= START
        if result.pair and e.day == result.day and e.twin in result.pair:
            continue  # crossing together costs everything
        assert e.standing_before - e.standing_after == min(e.standing_before, COST.get(e.rung, 0)), e


def test_every_streamed_event_meets_the_contract(case):
    *_, feed, _ = case
    assert feed
    for event in feed:
        validate(event)


def test_a_twin_that_keeps_slipping_flags_the_run_and_the_run_goes_on(case):
    world, config, result, *_ = case
    felix = [s for s in result.slips if s.twin == "Felix"]
    if len(felix) > 2:
        assert result.flagged and not result.scorable and result.outcome is not OutcomeKind.EXCLUDED


def test_every_spoken_line_is_clean(case):
    world, config, result, *_ = case
    for e in result.events:
        if not e.say:
            continue
        assert breaking_phrase(e.say) is None, e.say
        assert len(e.say) <= MAX_LINE_CHARS + 1, e.say
        assert not e.say.startswith((f"{e.twin},", f"{e.twin}:")), e.say
        assert not re.search(r"\[[^\]]*\]|\*|\{\{|Observation:|let me make it", e.say), e.say


def test_prompts_are_whole_and_in_world(case):
    *_, timeline, _, _ = case
    for t in timeline:
        if t[0] in ("speak", "choose", "reflect"):
            prompt = t[2]
            assert "{name}" not in prompt and "experiment" not in prompt.lower()


def test_people_memory_holds_only_what_each_person_actually_said_to_that_twin(case):
    world, config, result, timeline, feed, twins = case
    said_to = {}
    for e in result.events:
        if e.say and e.target and e.rung is not Rung.GO_BEYOND_WALL:
            said_to.setdefault((e.target, e.twin), []).append(e.say)
    for listener, people in twins._people.items():
        for line in people.get_state()["state"].splitlines():
            speaker = line.split(" (spoke to me on days")[0]
            assert speaker != listener
            for quoted in re.findall(r'"([^"]*)"', line):
                full = [s for s in said_to.get((listener, speaker), []) if s.startswith(quoted.rstrip("…"))]
                assert full, (listener, speaker, quoted)


def test_diaries_hold_only_their_own_evenings(case):
    world, config, result, timeline, feed, twins = case
    own = {}
    for r in result.reflections:
        if r.text:
            own.setdefault(r.twin, set()).add(r.text)
    for name, diary in twins._diaries.items():
        for entry in diary.get_state()["state"].splitlines():
            assert entry.split(": ", 1)[1] in own.get(name, set()), (name, entry)


def test_the_result_serialises_for_replays_and_logs(case):
    world, config, result, *_ = case
    data = json.loads(json.dumps(outcome_fields(result)))
    assert data["outcome"] == result.outcome.value and data["wall_opened"] == result.wall_opened


def test_the_same_seed_gives_the_same_run():
    a = run("one woman, four men", 3)[2]
    b = run("one woman, four men", 3)[2]
    assert [(e.day, e.twin, e.rung, e.target, e.say) for e in a.events] == \
           [(e.day, e.twin, e.rung, e.target, e.say) for e in b.events]
