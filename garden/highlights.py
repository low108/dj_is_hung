"""Highlights on results (C3): for each top candidate, 3 to 4 moments between her twin and his, plus one
pattern line, read from the finished runs.

The pattern line is computed from the scores, so its numbers are exact. A model (Gemini Flash by default)
only picks which moments to show and captions them in terms of feelings and dynamics. The model sees
what the twins did, never personas or dialogue (a twin's lines can repeat persona facts). Every caption
speaks of the twins, and one that echoes anything from a persona (job, age, home town, field of
study...) is replaced by a template caption: highlights carry no personal facts from the source data.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from . import world_text
from .batch import RunRecord
from .engine_types import Rung
from .scoring import CandidateScore

TOP = 3          # candidates that get highlights
MOST = 4         # highlights per candidate
FEWEST = 3
SHORTLIST = 12   # moments offered to the model
MAX_CAPTION = 160
BREAKOUT = "breakout"  # a run-level moment: they crossed the wall together


@dataclass(frozen=True)
class Style:
    weight: int      # most telling first
    act: str         # what happened, for the model's numbered list
    her: str         # template caption when her twin acted
    his: str         # template caption when his twin acted


STYLES = {
    BREAKOUT: Style(5, "crossed the wall together",
                    "Her twin and his twin chose each other over everything the Garden promised.",
                    "Her twin and his twin chose each other over everything the Garden promised."),
    Rung.GO_BEYOND_WALL.value: Style(4, "went to the wall for the other",
                                     "Her twin went to the wall for his twin, hoping he would follow.",
                                     "His twin went to the wall for her twin, and waited for her."),
    Rung.PROPOSE_LEAVING.value: Style(3, "asked the other to leave together",
                                      "Her twin wanted a life beyond the wall with his twin.",
                                      "His twin hoped her twin would leave the Garden with him."),
    Rung.SEEK_OUT.value: Style(2, "went looking for the other",
                               "Her twin couldn't stay away from his twin.",
                               "His twin kept finding his way back to her twin."),
    Rung.TALK.value: Style(1, "talked with the other",
                           "Her twin sought out a quiet moment with his twin.",
                           "His twin drew her twin into conversation."),
}

COMMON_WORDS = {  # short or everyday words a caption needs, whatever a persona happens to say
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "day", "did", "for", "had", "has", "her", "him",
    "his", "how", "in", "is", "it", "its", "new", "not", "of", "on", "one", "or", "out", "own", "she", "so",
    "the", "to", "too", "two", "was", "way", "who", "why", "yet", "all", "any", "can", "get", "got", "let",
    "met", "now", "off", "saw", "say", "see", "set", "try", "up", "us", "we", "he", "me", "my", "no", "do",
    "about", "after", "again", "always", "because", "before", "being", "could", "even", "every", "family",
    "from", "have", "home", "into", "just", "keep", "kept", "like", "love", "make", "more", "most", "much",
    "never", "often", "once", "only", "other", "people", "really", "some", "than", "that", "them", "then",
    "there", "they", "things", "think", "this", "time", "want", "wanted", "what", "when", "with", "would",
    "your", "good", "well", "were", "will", "very", "still", "each", "over", "away", "back", "close",
    "break", "breaks", "breaking", "broke", "rule", "rules", "follow", "followed", "open", "hard", "fall",
    "fell", "kind", "trust", "feel", "felt", "life", "hope", "hoped", "chose", "choose", "risk", "heart",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+|\d+", text.lower())


def _world_vocabulary() -> set[str]:
    """Every word the Garden's own text uses (wall, leave, Standing...): never a personal fact."""
    texts = [*world_text.WORLD_MEMORIES, *(s for s in (v for k, v in vars(world_text).items()
                                                       if k.startswith(("OBSERVE_", "ASK_"))))]
    texts += [str(o) for opts in world_text.RUNG_OPTIONS.values() for o in (
        opts if isinstance(opts, (list, tuple)) else [opts])]
    texts += [t for s in STYLES.values() for t in (s.act, s.her, s.his)]
    return {w for t in texts for w in _words(str(t))}


SAFE_WORDS = COMMON_WORDS | _world_vocabulary()


def personal_terms(personas: dict[str, str]) -> set[str]:
    """Words and numbers from the personas that a highlight must never echo."""
    return {w for text in personas.values() for w in _words(text) if w not in SAFE_WORDS}


def _echoes(word: str, terms: set[str]) -> bool:
    """The word, or a form of it (nurse / nursing), appears in a persona."""
    if word in SAFE_WORDS:
        return False
    return word in terms or (len(word) >= 4 and any(len(t) >= 4 and t[:4] == word[:4] for t in terms))


def acceptable(caption: str, terms: set[str]) -> bool:
    """About the twins, short, and echoing nothing from a persona."""
    words = _words(caption)
    return 0 < len(caption) <= MAX_CAPTION and "twin" in words and not any(_echoes(w, terms) for w in words)


@dataclass(frozen=True)
class Moment:
    run_id: str
    day: int
    kind: str               # a rung value, or BREAKOUT
    from_her: bool          # her twin acted (else his twin did)
    breakout: bool          # the run ended with them crossing the wall together

    @property
    def style(self) -> Style:
        return STYLES[self.kind]

    @property
    def template(self) -> str:
        return self.style.her if self.from_her else self.style.his


@dataclass(frozen=True)
class Highlight:
    run_id: str
    day: int
    kind: str
    from_her: bool
    caption: str
    label: str              # always about the twins, e.g. "Her twin and his twin · day 6"


@dataclass(frozen=True)
class CandidateHighlights:
    candidate: str
    pattern: str
    highlights: list[Highlight]
    source: str             # "model" if any caption came from the model, else "template"

    def to_dict(self) -> dict:
        return asdict(self)


def moments(records: list[RunRecord], woman: str, man: str) -> list[Moment]:
    """What her twin and his twin did toward each other in scored runs, most telling first. Each run
    they broke out of together is a moment too, so a candidate she broke out with always has three
    different ones: the breakout and the two choices that made it (wall and wall, or proposal and wall)."""
    out = []
    for rec in records:
        res = rec.result
        if res is None or not res.scorable:
            continue
        spec = rec.spec
        broke_out = bool(res.pair and set(res.pair) == {woman, man})
        if broke_out:
            out.append(Moment(spec.run_id, res.day, BREAKOUT, True, True))
        for e in res.events:
            if e.rung.value in STYLES and {e.twin, e.target} == {woman, man}:
                out.append(Moment(spec.run_id, e.day, e.rung.value, e.twin == woman, broke_out))
    return sorted(out, key=lambda m: (-m.style.weight, not m.breakout, m.run_id, m.day))


def pattern_line(score: CandidateScore) -> str:
    """One exact sentence from the scores (for a candidate she chose)."""
    k, n = score.chosen, score.runs
    crossed = f" They crossed together in {score.breakouts}." if score.breakouts else ""
    return f"Her twin tried to leave the Garden with his twin in {k} of the {n} runs where they had a date.{crossed}"


PROMPT = """You are choosing highlights from simulated dates between two AI twins in a walled Garden.
Crossing the wall together is how twins choose each other; it costs Standing, and Standing brings Pairing Day.
"Her twin" is the woman's twin; "his twin" is the man's twin.

Moments (numbered):
{moments}

Pick {low} to {high} different moments that best show how her twin feels about his twin. For each, write one
caption under 25 words about feelings and dynamics between the twins. Always say "her twin" and "his twin".
Never mention jobs, studies, ages, places, hobbies or any other personal facts.

Answer with JSON only: [{{"moment": <number>, "caption": "<caption>"}}, ...]"""


def _describe(i: int, m: Moment) -> str:
    who = "they" if m.kind == BREAKOUT else ("her twin" if m.from_her else "his twin")
    outcome = "they broke out together" if m.breakout else "no breakout together"
    return f"{i}. day {m.day}: {who} {m.style.act} ({outcome})"


def _parse(text: str) -> list[dict]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _highlight(m: Moment, caption: str) -> Highlight:
    label = f"Her twin and his twin · day {m.day}"
    return Highlight(m.run_id, m.day, m.kind, m.from_her, caption, label)


def pick(candidates: list[Moment], terms: set[str], model=None) -> tuple[list[Highlight], str]:
    """3 to 4 highlights (when there are enough moments), no caption shown twice. The model picks and
    captions; anything it gets wrong falls back to the most telling moments with template captions."""
    # One of each kind of moment first (each its most telling), then the rest, so the shortlist isn't
    # twelve breakouts that all read the same.
    seen_kinds: set[tuple[str, bool]] = set()
    firsts = [m for m in candidates if (m.kind, m.from_her) not in seen_kinds
              and not seen_kinds.add((m.kind, m.from_her))]
    shortlist = (firsts + [m for m in candidates if m not in firsts])[:SHORTLIST]
    chosen: list[Highlight] = []
    used: set[int] = set()
    shown: set[str] = set()
    source = "template"

    def add(i: int, caption: str) -> bool:
        if i in used or caption in shown or len(chosen) >= MOST:
            return False
        chosen.append(_highlight(shortlist[i], caption))
        used.add(i)
        shown.add(caption)
        return True

    if model is not None and shortlist:
        prompt = PROMPT.format(moments="\n".join(_describe(i + 1, m) for i, m in enumerate(shortlist)),
                               low=min(FEWEST, len(shortlist)), high=min(MOST, len(shortlist)))
        try:
            answer = _parse(model.sample_text(prompt))
        except Exception:  # quota, network: highlights are a nicety, the results still show
            answer = []
        for item in answer:
            i = item.get("moment")
            if type(i) is not int or not 1 <= i <= len(shortlist):  # (True is an int; it isn't a moment)
                continue
            caption = str(item.get("caption", "")).strip()
            if acceptable(caption, terms):
                if add(i - 1, caption):
                    source = "model"
            else:
                add(i - 1, shortlist[i - 1].template)
    for i, m in enumerate(shortlist):  # top up with the most telling moments not yet shown
        if len(chosen) >= FEWEST:
            break
        add(i, m.template)
    return chosen, source


def for_simulation(records: list[RunRecord], scores: list[CandidateScore], woman: str,
                   personas: dict[str, str], model=None) -> list[CandidateHighlights]:
    """Highlights for the top candidates her twin broke out with (best first)."""
    terms = personal_terms(personas)
    out = []
    for score in [s for s in scores if s.chosen][:TOP]:
        chosen, source = pick(moments(records, woman, score.candidate), terms, model)
        out.append(CandidateHighlights(score.candidate, pattern_line(score), chosen, source))
    return out
