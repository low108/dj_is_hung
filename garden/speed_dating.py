"""Twins from the Columbia Speed Dating dataset (Fisman, Iyengar, Kamenica & Simonson, 2006).

Only fields collected BEFORE the dates reach a twin. Decisions, partner ratings and follow-up
surveys are the answer key and never leave this module's allow-list.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .paths import DATA_DIR

DEFAULT_PATH = DATA_DIR / "raw" / "speed_dating.csv"

INTERESTS = ["sports", "tvsports", "exercise", "dining", "museums", "art", "hiking", "gaming", "clubbing",
             "reading", "tv", "theater", "movies", "concerts", "music", "shopping", "yoga"]
INTEREST_WORDS = {"tvsports": "watching sports on TV", "tv": "TV", "gaming": "gaming", "clubbing": "clubbing",
                  "dining": "dining out", "museums": "museums", "art": "art", "hiking": "hiking",
                  "reading": "reading", "theater": "theater", "movies": "movies", "concerts": "concerts",
                  "music": "music", "shopping": "shopping", "yoga": "yoga", "sports": "playing sports",
                  "exercise": "exercise"}
ATTRS = {"attr": "attractive", "sinc": "sincere", "intel": "intelligent", "fun": "fun", "amb": "ambitious",
         "shar": "someone who shares my interests"}

# The allow-list: every field a twin may be built from. Anything else is never read.
PRE_DATE_FIELDS = (
    ["iid", "gender", "wave", "age", "field", "career", "from", "goal", "date", "go_out", "imprace", "imprelig"]
    + INTERESTS
    + [f"{a}1_1" for a in ATTRS]                       # what they look for in a partner
    + [f"{a}3_1" for a in ATTRS if a != "shar"]        # how they rate themselves
)

# Codebook (dataset key)
GOAL = {1: "it seemed like a fun night out", 2: "I wanted to meet new people", 3: "I wanted to get a date",
        4: "I'm looking for a serious relationship", 5: "I wanted to say I did it", 6: "of other reasons"}
FREQUENCY = {1: "several times a week", 2: "twice a week", 3: "once a week", 4: "twice a month",
             5: "once a month", 6: "several times a year", 7: "almost never"}


def load(path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    """One row per date. Raises with download instructions if the file isn't there."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download 'Speed Dating Data.csv' from "
            "https://www.kaggle.com/annavictoria/speed-dating-experiment and save it there."
        )
    return pd.read_csv(path, encoding="latin-1")


def profile(dates: pd.DataFrame, iid: int) -> dict:
    """A participant's pre-date answers, allow-listed. Missing values are dropped."""
    rows = dates[dates["iid"] == iid]
    if rows.empty:
        raise KeyError(f"no participant with iid {iid}")
    row = rows.iloc[0][PRE_DATE_FIELDS].to_dict()
    return {k: v for k, v in row.items() if not (isinstance(v, float) and math.isnan(v))}


@dataclass(frozen=True)
class Memory:
    text: str
    source: str  # the dataset field(s) it came from, e.g. "career" or "attr1_1,sinc1_1"


@dataclass
class TwinRecord:
    alias: str
    iid: int
    gender: str
    memories: list[Memory] = field(default_factory=list)

    def persona_text(self) -> str:
        return "\n".join(m.text for m in self.memories)


def _num(p: dict, key: str) -> float | None:
    v = p.get(key)
    try:
        return float(str(v).replace(",", "")) if v is not None else None
    except ValueError:
        return None


def template_memories(p: dict) -> list[Memory]:
    """Deterministic first-person memories, one per fact, each citing its source field."""
    out: list[Memory] = []
    add = lambda text, source: out.append(Memory(text, source))  # noqa: E731

    if (age := _num(p, "age")) is not None:
        add(f"I am {int(age)} years old.", "age")
    if p.get("field"):
        add(f"I study {str(p['field']).strip()}.", "field")
    if p.get("career"):
        add(f"My career plans: {str(p['career']).strip()}.", "career")
    if p.get("from"):
        add(f"Before university, I lived in {str(p['from']).strip()}.", "from")
    if (g := _num(p, "goal")) in GOAL:
        add(f"I came to meet people because {GOAL[int(g)]}.", "goal")
    if (d := _num(p, "date")) in FREQUENCY:
        add("I almost never go on dates." if d == 7 else f"I go on dates {FREQUENCY[int(d)]}.", "date")
    if (o := _num(p, "go_out")) in FREQUENCY:
        add("I almost never go out." if o == 7 else f"I go out {FREQUENCY[int(o)]}.", "go_out")

    scored = sorted(((k, _num(p, k)) for k in INTERESTS if _num(p, k) is not None), key=lambda kv: -kv[1])
    loves = [k for k, v in scored if v >= 8][:4]
    dislikes = [k for k, v in scored if v <= 3][:3]
    if loves:
        add(f"I love {', '.join(INTEREST_WORDS[k] for k in loves)}.", ",".join(loves))
    if dislikes:
        add(f"I don't care much for {', '.join(INTEREST_WORDS[k] for k in dislikes)}.", ",".join(dislikes))

    wants = {a: _num(p, f"{a}1_1") for a in ATTRS}
    wants = {a: v for a, v in wants.items() if v is not None}
    if wants and (total := sum(wants.values())) > 0:  # some events used points out of 100, others 1-10
        top = sorted(wants, key=lambda a: -wants[a])[:2]
        add(f"In a partner, what matters most to me is that they are {ATTRS[top[0]]}, then {ATTRS[top[1]]}.",
            ",".join(f"{a}1_1" for a in top))
        low = min(wants, key=lambda a: wants[a])
        if wants[low] / total < 0.12:
            add(f"Whether a partner is {ATTRS[low]} matters less to me.", f"{low}1_1")

    selfs = {a: _num(p, f"{a}3_1") for a in ATTRS if a != "shar"}
    strong = [a for a, v in selfs.items() if v is not None and v >= 9]
    modest = [a for a, v in selfs.items() if v is not None and v <= 5]
    if strong:
        add(f"I think of myself as very {' and '.join(ATTRS[a] for a in strong)}.", ",".join(f"{a}3_1" for a in strong))
    if modest:
        add(f"I don't see myself as especially {' or '.join(ATTRS[a] for a in modest)}.", ",".join(f"{a}3_1" for a in modest))

    if (r := _num(p, "imprelig")) is not None and r >= 7:
        add("It matters to me that a partner shares my religion.", "imprelig")
    if (r := _num(p, "imprace")) is not None and r >= 7:
        add("It matters to me that a partner shares my background.", "imprace")
    return out


REWRITE_PROMPT = """Rewrite each fact below as one natural sentence this person would say about themselves,
in the first person, in a warm, conversational voice. Do not start with "I remember".
Rules: keep every fact true to what it says; add no new facts, names, places, numbers or events;
one sentence each; copy each fact's "source" exactly.
Reply with only a JSON list of objects with keys "memory" and "source".

Facts:
{facts}
"""


def validate_rewrite(items: list[dict], facts: list[Memory]) -> list[Memory]:
    """Keep rewritten memories only if they cite a real source and add no numbers the fact didn't have."""
    by_source = {m.source: m for m in facts}
    kept = []
    for item in items:
        source, text = str(item.get("source", "")), str(item.get("memory", "")).strip()
        fact = by_source.get(source)
        if not fact or not text:
            continue  # unsourced or unknown source: rejected
        if set(re.findall(r"\d+", text)) - set(re.findall(r"\d+", fact.text)):
            continue  # invented numbers: rejected
        kept.append(Memory(text, source))
    return kept


def rewrite_memories(facts: list[Memory], model) -> list[Memory]:
    """Ask a language model to make the template memories sound natural; fall back per fact on rejection."""
    payload = json.dumps([{"fact": m.text, "source": m.source} for m in facts], indent=1)
    raw = model.sample_text(REWRITE_PROMPT.format(facts=payload), max_tokens=1500, temperature=0.4)
    match = re.search(r"\[.*\]", raw, re.S)
    try:
        items = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        items = []
    kept = {m.source: m for m in validate_rewrite(items, facts)}
    return [kept.get(f.source, f) for f in facts]


ALIASES = {
    "f": ["Mara", "Lina", "Iris", "Noor", "Ada", "Yuki", "Elena", "Priya", "Sofia", "Hana", "Leila", "Maya",
          "Clara", "Aisha", "Nadia", "Ines", "Mei", "Zara", "Ana", "Tara"],
    "m": ["Ren", "Jun", "Theo", "Kai", "Sam", "Omar", "Luca", "Arjun", "Mateo", "Hugo", "Ilan", "Kenji",
          "Ravi", "Felix", "Tomas", "Amir", "Leo", "Daniel", "Ezra", "Marco"],
}


def alias_for(iid: int, gender: str) -> str:
    names = ALIASES[gender]
    base = names[iid % len(names)]
    return base if iid < len(names) else f"{base} {chr(65 + (iid // len(names)) % 26)}."


def build_twin(dates: pd.DataFrame, iid: int, model=None) -> TwinRecord:
    p = profile(dates, iid)
    gender = "m" if int(p["gender"]) == 1 else "f"
    facts = template_memories(p)
    memories = rewrite_memories(facts, model) if model is not None else facts
    return TwinRecord(alias=alias_for(iid, gender), iid=iid, gender=gender, memories=memories)
