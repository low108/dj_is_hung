"""About you: the structured part of onboarding, next to the open questions (garden/onboarding.py).

Three short forms, each turned into first-person facts the twin knows, worded by fixed templates (no model
call, so nothing is invented):

- Profile: age, work or studies, city, and the interests the user loves or doesn't care for. These are
  the concrete details that made the dataset twins' dates feel alive (courts, cinemas, law school); without
  them a twin invents a career.
- Personality: the Mini-IPIP, 20 statements rated 1-5 (Donnellan, Oswald, Baird & Lucas, 2006). Its items
  are from the International Personality Item Pool and in the public domain (the BFI-2 used by the couples
  data is copyrighted for commercial use). Each Big Five trait is the mean of its 4 items, reverse-keyed
  where marked; a clearly high or low trait (>= 3.75 or <= 2.25 on 1-5) becomes one sentence.
- What matters in a partner: 100 points across six qualities, as the Columbia speed-dating study asked.

User twins also get STRICT_GROUNDING: they are real people, so the twin must not invent facts about them.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

INTERESTS = {
    "sports": "playing sports", "tvsports": "watching sports", "exercise": "exercise", "dining": "dining out",
    "museums": "museums", "art": "art", "hiking": "hiking", "gaming": "gaming", "clubbing": "clubbing",
    "reading": "reading", "tv": "TV", "theater": "theater", "movies": "movies", "concerts": "concerts",
    "music": "music", "shopping": "shopping", "yoga": "yoga", "cooking": "cooking", "travel": "travel",
}
QUALITIES = {"attractive": "attractive", "sincere": "sincere", "intelligent": "intelligent", "fun": "fun",
             "ambitious": "ambitious", "shared_interests": "someone who shares my interests"}

# The Mini-IPIP: (id, statement, trait, reverse-keyed). Rated 1 (very inaccurate) to 5 (very accurate).
MINI_IPIP = (
    ("e1", "Am the life of the party.", "E", False),
    ("a1", "Sympathize with others' feelings.", "A", False),
    ("c1", "Get chores done right away.", "C", False),
    ("n1", "Have frequent mood swings.", "N", False),
    ("i1", "Have a vivid imagination.", "I", False),
    ("e2", "Don't talk a lot.", "E", True),
    ("a2", "Am not interested in other people's problems.", "A", True),
    ("c2", "Often forget to put things back in their proper place.", "C", True),
    ("n2", "Am relaxed most of the time.", "N", True),
    ("i2", "Am not interested in abstract ideas.", "I", True),
    ("e3", "Talk to a lot of different people at parties.", "E", False),
    ("a3", "Feel others' emotions.", "A", False),
    ("c3", "Like order.", "C", False),
    ("n3", "Get upset easily.", "N", False),
    ("i3", "Have difficulty understanding abstract ideas.", "I", True),
    ("e4", "Keep in the background.", "E", True),
    ("a4", "Am not really interested in others.", "A", True),
    ("c4", "Make a mess of things.", "C", True),
    ("n4", "Seldom feel blue.", "N", True),
    ("i4", "Do not have a good imagination.", "I", True),
)
ITEMS = {i[0]: i for i in MINI_IPIP}
TRAITS = {"E": "Extraversion", "A": "Agreeableness", "C": "Conscientiousness", "N": "Neuroticism",
          "I": "Intellect/Imagination"}
HIGH, LOW = 3.75, 2.25  # a trait this far from the middle of the 1-5 scale says something
SAYS = {  # trait -> (high, low), in the twin's own words
    "E": ("I'm outgoing; I talk to everyone at a party.", "I'm on the quiet side; I'd rather keep to the background."),
    "A": ("I feel other people's emotions and care about their problems.", "I don't get very involved in other people's problems."),
    "C": ("I like order and get things done right away.", "I'm not the tidiest; things don't always go back in their place."),
    "N": ("My moods can swing, and I get upset easily.", "I'm relaxed most of the time and rarely feel blue."),
    "I": ("I have a vivid imagination and love abstract ideas.", "I'm practical rather than imaginative."),
}

STRICT_GROUNDING = ("Everything I say about my own life comes from what I know here; if I'm asked about something "
                    "I don't know about myself, I keep it general rather than make it up.")


class Profile(BaseModel):
    age: int = Field(ge=18, le=99)
    work: str = Field(min_length=1, max_length=80, description="What I do or study")
    city: str = Field(min_length=1, max_length=80)
    loves: list[str] = Field(default_factory=list, max_length=6)
    dislikes: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("loves", "dislikes")
    @classmethod
    def known_interests(cls, v: list[str]) -> list[str]:
        unknown = [i for i in v if i not in INTERESTS]
        if unknown:
            raise ValueError(f"unknown interests: {unknown}")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def not_both(self) -> "Profile":
        if set(self.loves) & set(self.dislikes):
            raise ValueError("an interest can't be both loved and disliked")
        return self


class Personality(BaseModel):
    answers: dict[str, int]

    @field_validator("answers")
    @classmethod
    def all_items_1_to_5(cls, v: dict[str, int]) -> dict[str, int]:
        if set(v) != set(ITEMS):
            raise ValueError(f"answer all {len(ITEMS)} statements")
        if any(not 1 <= x <= 5 for x in v.values()):
            raise ValueError("each answer is 1 (very inaccurate) to 5 (very accurate)")
        return v


class Preferences(BaseModel):
    points: dict[str, int]

    @field_validator("points")
    @classmethod
    def hundred_points(cls, v: dict[str, int]) -> dict[str, int]:
        if set(v) != set(QUALITIES) or any(x < 0 for x in v.values()):
            raise ValueError(f"give points (0 or more) to each of: {', '.join(QUALITIES)}")
        if sum(v.values()) != 100:
            raise ValueError(f"the points must add up to 100 (they add up to {sum(v.values())})")
        return v


def trait_scores(p: Personality) -> dict[str, float]:
    """Each trait's mean on 1-5, reverse-keyed items flipped (6 - answer)."""
    by_trait: dict[str, list[int]] = {t: [] for t in TRAITS}
    for item, answer in p.answers.items():
        _, _, trait, reverse = ITEMS[item]
        by_trait[trait].append(6 - answer if reverse else answer)
    return {t: sum(v) / len(v) for t, v in by_trait.items()}


def _list(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def memories(about: dict) -> list[dict]:
    """The twin's facts from the forms the user filled in, each tagged with what it's about."""
    out: list[dict] = []
    add = lambda text, kind: out.append({"text": text, "about": kind})  # noqa: E731
    if about.get("profile"):
        p = Profile(**about["profile"])
        add(f"I am {p.age} years old.", "age")
        add(f"My work: {p.work.strip().rstrip('.')}.", "career")
        add(f"I live in {p.city.strip().rstrip('.')}.", "home")
        if p.loves:
            add(f"I love {_list([INTERESTS[i] for i in p.loves])}.", "loves")
        if p.dislikes:
            add(f"I don't care much for {_list([INTERESTS[i] for i in p.dislikes])}.", "not for me")
    if about.get("personality"):
        for trait, score in trait_scores(Personality(**about["personality"])).items():
            if score >= HIGH:
                add(SAYS[trait][0], "personality")
            elif score <= LOW:
                add(SAYS[trait][1], "personality")
    if about.get("preferences"):
        pts = Preferences(**about["preferences"]).points
        top = sorted(pts, key=lambda q: -pts[q])[:2]
        add(f"In a partner, what matters most to me is that they are {QUALITIES[top[0]]}, then {QUALITIES[top[1]]}.",
            "wants in a partner")
        low = min(pts, key=lambda q: pts[q])
        if pts[low] < 12:
            add(f"Whether a partner is {QUALITIES[low]} matters less to me.", "wants in a partner")
    return out


def status(about: dict | None) -> dict:
    about = about or {}
    return {part: bool(about.get(part)) for part in ("profile", "personality", "preferences")}


def form() -> dict:
    """What the onboarding screen needs to draw the three forms."""
    return {"interests": INTERESTS, "qualities": QUALITIES,
            "statements": [{"id": i, "text": text} for i, text, _, _ in MINI_IPIP]}
