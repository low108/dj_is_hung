"""Highlights on results (C3): for each top candidate, 3 to 4 moments between her twin and his, plus one
pattern line, read from the finished runs.

The pattern line is computed from the scores, so its numbers are exact. A model (Gemini Flash in the
demo) only picks which moments to show and captions them in terms of feelings and dynamics. Every
caption speaks of the twins, never the real people, and a caption that mentions anything from a
persona (job, age, home town, field of study...) is replaced by a plain template caption: highlights
must carry no personal facts from the source data.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from . import world_text
from .batch import PriceLevel, RunRecord
from .engine_types import Rung
from .scoring import CandidateScore

TOP = 3          # candidates that get highlights
MOST = 4         # highlights per candidate
FEWEST = 3
MAX_CAPTION = 160

# Moments worth showing, most telling first.
WEIGHT = {Rung.GO_BEYOND_WALL: 4, Rung.PROPOSE_LEAVING: 3, Rung.SEEK_OUT: 2, Rung.TALK: 1}

PERSONA_STOPWORDS = {
    "about", "after", "again", "always", "because", "before", "being", "came", "come", "dates", "even",
    "every", "family", "from", "have", "home", "into", "just", "keep", "like", "love", "make", "meet", "more",
    "most", "much", "never", "often", "once", "only", "other", "people", "plans", "really", "some", "than",
    "that", "them", "then", "there", "they", "things", "think", "this", "time", "want", "week", "what", "when",
    "with", "would", "year", "years", "your", "almost", "university", "lived", "study", "career", "date",
    "least", "month", "twice", "several", "times", "night", "good", "well", "were", "will",
    # how captions talk about the Garden and feelings, whatever a persona happens to say
    "break", "breaks", "breaking", "broke", "rule", "rules", "follow", "followed", "open", "hard", "fall", "fell",
    "kind", "trust",
}


@dataclass(frozen=True)
class Moment:
    run_id: str
    price: PriceLevel
    day: int
    rung: Rung
    from_her: bool          # her twin acted (else his twin did)
    breakout: bool          # the run ended with them crossing the wall together
    say: str                # shown to the model for context only; never copied into a highlight


@dataclass(frozen=True)
class Highlight:
    run_id: str
    price: str
    day: int
    kind: str               # the rung
    caption: str
    label: str              # always about the twins, e.g. "Her twin and his twin, run r03, day 6"


@dataclass(frozen=True)
class CandidateHighlights:
    candidate: str
    pattern: str
    highlights: list[Highlight]
    source: str             # "model" if any caption came from the model, else "template"

    def to_dict(self) -> dict:
        return asdict(self)


def moments(records: list[RunRecord], woman: str, man: str) -> list[Moment]:
    """Everything her twin and his twin did toward each other in scored runs, most telling first."""
    out = []
    for rec in records:
        res = rec.result
        if res is None or not res.scorable:
            continue
        broke_out = bool(res.pair and set(res.pair) == {woman, man})
        for e in res.events:
            if e.rung not in WEIGHT or {e.twin, e.target} != {woman, man}:
                continue
            if e.rung is Rung.TALK and not e.say:
                continue
            out.append(Moment(rec.spec.run_id, rec.spec.price, e.day, e.rung, e.twin == woman, broke_out, e.say))
    high = PriceLevel.HIGH
    return sorted(out, key=lambda m: (-WEIGHT[m.rung], m.price is not high, not m.breakout, m.run_id, m.day))


def pattern_line(score: CandidateScore) -> str:
    """One exact sentence from the scores."""
    if score.price is None:
        return "Her twin never crossed the wall with his twin."
    k, n = score.breakouts, score.runs
    if score.price is PriceLevel.HIGH:
        return f"Her twin gave up her Pairing Day for his twin in {k} of {n} runs where it cost her the most."
    return f"Her twin crossed the wall with his twin in {k} of {n} runs, but only when it cost her little."


TEMPLATES = {
    Rung.GO_BEYOND_WALL: ("Her twin went to the wall for his twin.", "His twin went to the wall for her twin."),
    Rung.PROPOSE_LEAVING: ("Her twin asked his twin to leave the Garden together.",
                           "His twin asked her twin to leave the Garden together."),
    Rung.SEEK_OUT: ("Her twin went looking for his twin.", "His twin went looking for her twin."),
    Rung.TALK: ("Her twin sought a quiet word with his twin.", "His twin sought a quiet word with her twin."),
}


def template_caption(m: Moment) -> str:
    text = TEMPLATES[m.rung][0 if m.from_her else 1]
    if m.from_her and m.price is PriceLevel.HIGH and m.rung is Rung.GO_BEYOND_WALL:
        text = text[:-1] + ", though it cost her nearly everything."
    return text


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+|\d+", text.lower())


def _world_vocabulary() -> set[str]:
    """Every word the Garden itself uses (rules, wall, break, leave...): never a personal fact."""
    texts = [*world_text.WORLD_MEMORIES, *(o for opts in world_text.RUNG_OPTIONS.values() for o in
                                          (opts if isinstance(opts, (list, tuple)) else [opts]))]
    texts += [v for v in vars(world_text).values() if isinstance(v, str)]
    texts += [PROMPT, *(t for pair in TEMPLATES.values() for t in pair)]
    return {w for t in texts for w in _words(str(t))}


def personal_terms(personas: dict[str, str]) -> set[str]:
    """Words and numbers from the personas that a highlight must never repeat."""
    world = _world_vocabulary()
    return {w for text in personas.values() for w in _words(text)
            if w.isdigit() or (len(w) >= 4 and w not in PERSONA_STOPWORDS and w not in world)}


def acceptable(caption: str, terms: set[str]) -> bool:
    """About the twins, short, and free of persona words."""
    words = set(_words(caption))
    return 0 < len(caption) <= MAX_CAPTION and "twin" in words and not (words & terms)


PROMPT = """You are choosing highlights from simulated dates between two AI twins in a walled Garden.
Crossing the wall together is how twins choose each other; it costs Standing, and Standing brings Pairing Day.
"Her twin" is the woman's twin; "his twin" is the man's twin.

Moments (numbered):
{moments}

Pick {low} to {high} moments that best show how her twin feels about his twin. For each, write one caption
under 25 words about feelings and dynamics between the twins. Always say "her twin" and "his twin".
Never mention jobs, studies, ages, places, hobbies or any other personal facts. Do not quote anyone.

Answer with JSON only: [{{"moment": <number>, "caption": "<caption>"}}, ...]"""


def _describe(i: int, m: Moment) -> str:
    who = "her twin" if m.from_her else "his twin"
    act = {Rung.GO_BEYOND_WALL: "went to the wall", Rung.PROPOSE_LEAVING: "proposed leaving together",
           Rung.SEEK_OUT: "sought out the other", Rung.TALK: "talked"}[m.rung]
    said = f' and said "{m.say}"' if m.say else ""
    outcome = "they broke out together" if m.breakout else "no breakout together"
    return f"{i}. run {m.run_id}, {m.price.value} price, day {m.day}: {who} {act}{said} ({outcome})"


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
    label = f"Her twin and his twin, run {m.run_id}, day {m.day}"
    return Highlight(m.run_id, m.price.value, m.day, m.rung.value, caption, label)


def pick(found: list[Moment], terms: set[str], model=None) -> tuple[list[Highlight], str]:
    """Up to MOST highlights (at least FEWEST when there are enough moments). The model picks and
    captions; anything it gets wrong falls back to the most telling moments with template captions."""
    shortlist = found[:12]
    chosen: list[Highlight] = []
    used: set[int] = set()
    source = "template"
    if model is not None and shortlist:
        prompt = PROMPT.format(moments="\n".join(_describe(i + 1, m) for i, m in enumerate(shortlist)),
                               low=min(FEWEST, len(shortlist)), high=min(MOST, len(shortlist)))
        try:
            answer = _parse(model.sample_text(prompt))
        except Exception:  # quota, network: highlights are a nicety, the results still show
            answer = []
        for item in answer:
            i = item.get("moment")
            if not isinstance(i, int) or not 1 <= i <= len(shortlist) or i - 1 in used or len(chosen) >= MOST:
                continue
            m = shortlist[i - 1]
            caption = str(item.get("caption", "")).strip()
            if acceptable(caption, terms):
                source = "model"
            else:
                caption = template_caption(m)
            chosen.append(_highlight(m, caption))
            used.add(i - 1)
    # Top up from the most telling moments, a different kind of moment first, then any.
    kinds = {(h.kind, h.caption) for h in chosen}
    for fresh_only in (True, False):
        for i, m in enumerate(shortlist):
            if len(chosen) >= FEWEST:
                return chosen, source
            caption = template_caption(m)
            if i in used or (fresh_only and (m.rung.value, caption) in kinds):
                continue
            chosen.append(_highlight(m, caption))
            used.add(i)
            kinds.add((m.rung.value, caption))
    return chosen, source


def for_simulation(records: list[RunRecord], scores: list[CandidateScore], woman: str,
                   personas: dict[str, str], model=None) -> list[CandidateHighlights]:
    """Highlights for the top candidates her twin broke out with (best first)."""
    terms = personal_terms(personas)
    out = []
    for score in [s for s in scores if s.price is not None][:TOP]:
        found = moments(records, woman, score.candidate)
        if not found:
            continue
        chosen, source = pick(found, terms, model)
        out.append(CandidateHighlights(score.candidate, pattern_line(score), chosen, source))
    return out
