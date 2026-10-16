"""Couples pools (real personality): twins built from both partners' Big Five facets in real couples.

Data: Weidmann, Purol et al. (2023), "Trait and facet personality similarity and relationship and life
satisfaction in romantic couples", Journal of Research in Personality; OSF kze6c, file
`datasimilarity.csv`. 1,294 female-male couples (together 30 years on average). Personality is the
BFI-2-S (1-5); relationship satisfaction is the 5-item Quality of Marriage Index (1-5). In the file P1 is
the female and P2 the male partner (their satisfaction means, 4.42 and 4.47, match the paper's Table 1).
Trait and facet columns are centred on the couple-pooled mean; adding back the paper's Table 1 means
restores the 1-5 scores. Aesthetic sensitivity is missing: its column is a duplicate of emotional
volatility in the released file, so 14 of the 15 facets are used.

A pool is one woman, her real partner (the answer key) and DECOYS men from other couples. A persona is
the twin's most distinctive facets (relative to their own gender), each as one first-person sentence.
The file has no age, job or interests: these twins are personality only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random

import pandas as pd

from .paths import DATA_DIR

DEFAULT_PATH = DATA_DIR / "raw" / "couples_weidmann2023.csv"
DECOYS = 6          # men from other couples alongside her real partner
FACETS_SHOWN = 6    # facets per persona: the most distinctive ones
MIN_Z = 0.5         # a facet is "distinctive" when at least this far from their gender's mean (in SDs)

# Paper Table 1: (male mean, male SD, female mean, female SD) per facet, on the 1-5 BFI-2 scale.
TABLE1 = {
    "Sociability": (3.15, 1.06, 3.25, 1.03),
    "Assertiveness": (3.54, 0.98, 2.99, 1.01),
    "EnergyLevel": (3.52, 1.01, 3.47, 1.03),
    "Compassion": (3.84, 0.91, 4.23, 0.78),
    "Respectfulness": (3.99, 0.86, 4.26, 0.77),
    "Trust": (3.45, 0.95, 3.69, 0.93),
    "Organization": (3.72, 1.10, 3.91, 1.05),
    "Productiveness": (3.93, 0.89, 3.95, 0.90),
    "Responsibility": (4.05, 0.79, 4.15, 0.76),
    "Anxiety": (2.41, 1.00, 2.83, 1.06),
    "DepressionB5": (1.91, 0.87, 2.15, 0.98),
    "EmotionalVolatility": (2.25, 0.97, 2.57, 1.02),
    "IntellectualCuriosity": (3.47, 0.94, 3.32, 0.89),
    "CreativeImagination": (3.63, 0.95, 3.66, 0.92),
}

# How each facet sounds, high and low, in the twin's own words (after the BFI-2 item content).
SAYS = {
    "Sociability": ("I'm outgoing and sociable; I love being around people.",
                    "I'm quiet and reserved; I prefer my own company or a few close people."),
    "Assertiveness": ("I'm assertive: I say what I think and I like to take charge.",
                      "I tend to hold back and let others take the lead."),
    "EnergyLevel": ("I'm full of energy and enthusiasm.",
                    "I'm low-key; I rarely get excited or rush about."),
    "Compassion": ("I'm warm and caring; I feel for anyone who is struggling.",
                   "I don't get very involved in other people's problems."),
    "Respectfulness": ("I'm respectful and polite; I treat everyone as an equal.",
                       "I can be blunt or rude, and I don't mind an argument."),
    "Trust": ("I assume the best about people and trust them easily.",
              "I'm wary of people's intentions; trust has to be earned."),
    "Organization": ("I'm neat and organized; I like things in order.",
                     "I'm disorganized and don't mind a bit of mess."),
    "Productiveness": ("I'm efficient: once I start something, I finish it.",
                       "I put things off and find it hard to get going."),
    "Responsibility": ("I'm dependable; people can count on me.",
                       "I can be careless and don't always follow through."),
    "Anxiety": ("I worry a lot and get nervous easily.",
                "I'm relaxed and handle stress well."),
    "DepressionB5": ("I often feel sad or down.",
                     "I'm generally content and feel good about myself."),
    "EmotionalVolatility": ("My moods go up and down, and I get upset easily.",
                            "I'm emotionally steady; I rarely lose my temper."),
    "IntellectualCuriosity": ("I'm curious about everything and I love complex ideas.",
                              "I'm not much interested in abstract ideas or deep discussions."),
    "CreativeImagination": ("I'm inventive and original; I'm always coming up with new ideas.",
                            "I'm practical and down to earth rather than imaginative."),
}

WOMEN = ("Ada", "Bea", "Cleo", "Dora", "Edie", "Faye", "Gwen", "Hana", "Ines", "June", "Kira", "Lena",
         "Maya", "Nina", "Opal", "Pia", "Rosa", "Sara", "Tess", "Vera")
MEN = ("Abe", "Ben", "Cal", "Dev", "Eli", "Finn", "Gus", "Hal", "Ivo", "Jon", "Kai", "Leo", "Max", "Ned",
       "Otto", "Paul", "Rex", "Sam", "Tom", "Wes")


@dataclass(frozen=True)
class Person:
    alias: str
    gender: str                 # "f" or "m"
    couple: int                 # row in the file
    scores: dict[str, float]    # facet -> 1-5 score
    memories: tuple[str, ...]   # the persona

    def persona_text(self) -> str:
        return "\n".join(self.memories)


@dataclass(frozen=True)
class CouplePool:
    woman: Person
    men: tuple[Person, ...]
    partner: str                # alias of her real partner: the answer key
    satisfaction: tuple[float, float]  # (hers, his), Quality of Marriage Index, 1-5


def load(path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: download datasimilarity.csv from https://osf.io/kze6c/ "
                                f"(Data folder) and save it there")
    return pd.read_csv(path)


def complete(data: pd.DataFrame) -> list[int]:
    """Couples with every facet and both satisfaction scores for both partners."""
    cols = [f"{f}C_P{p}" for f in TABLE1 for p in (1, 2)] + ["RelationshipSatisfaction_P1", "RelationshipSatisfaction_P2"]
    return [int(i) for i in data.index[data[cols].notna().all(axis=1)]]


def scores(data: pd.DataFrame, couple: int, partner: int) -> dict[str, float]:
    """1-5 facet scores: centred value + the couple-pooled mean (average of the male and female means)."""
    row = data.loc[couple]
    return {f: round(float(row[f"{f}C_P{partner}"]) + (m_mean + f_mean) / 2, 3)
            for f, (m_mean, _, f_mean, _) in TABLE1.items()}


def memories(facet_scores: dict[str, float], gender: str) -> tuple[str, ...]:
    """The FACETS_SHOWN facets furthest from their gender's mean (at least MIN_Z SDs), most distinctive first."""
    z = {}
    for f, s in facet_scores.items():
        m_mean, m_sd, f_mean, f_sd = TABLE1[f]
        mean, sd = (f_mean, f_sd) if gender == "f" else (m_mean, m_sd)
        z[f] = (s - mean) / sd
    picked = sorted((f for f in z if abs(z[f]) >= MIN_Z), key=lambda f: -abs(z[f]))[:FACETS_SHOWN]
    return tuple(SAYS[f][0 if z[f] > 0 else 1] for f in picked)


def person(data: pd.DataFrame, couple: int, partner: int, alias: str) -> Person:
    gender = "f" if partner == 1 else "m"
    s = scores(data, couple, partner)
    return Person(alias, gender, couple, s, memories(s, gender))


def load_pool(data: pd.DataFrame, couple: int, decoys: int = DECOYS) -> CouplePool:
    """Her twin, her real partner's twin and `decoys` men from other couples (chosen by the couple id, so
    the same couple always gets the same men). Names are drawn at random so the partner isn't marked out."""
    usable = complete(data)
    if couple not in usable:
        raise KeyError(f"couple {couple} is missing data")
    rng = Random(couple)
    others = rng.sample([c for c in usable if c != couple], decoys)
    names = list(MEN)
    rng.shuffle(names)
    woman = person(data, couple, 1, WOMEN[couple % len(WOMEN)])
    partner = person(data, couple, 2, names[0])
    men = [partner] + [person(data, c, 2, names[i + 1]) for i, c in enumerate(others)]
    men.sort(key=lambda p: p.alias)  # alphabetical, so the partner's position says nothing
    row = data.loc[couple]
    return CouplePool(woman, tuple(men), partner.alias,
                      (float(row["RelationshipSatisfaction_P1"]), float(row["RelationshipSatisfaction_P2"])))


def pick_couples(data: pd.DataFrame, n_happy: int = 3, n_unhappy: int = 3, seed: int = 0) -> dict[str, list[int]]:
    """Couples at both ends of satisfaction: both partners 5.0 (happy) or both 3.0 or lower (unhappy)."""
    rng = Random(seed)
    usable = data.loc[complete(data)]
    happy = sorted(int(i) for i in usable.index[(usable.RelationshipSatisfaction_P1 >= 5) & (usable.RelationshipSatisfaction_P2 >= 5)])
    unhappy = sorted(int(i) for i in usable.index[(usable.RelationshipSatisfaction_P1 <= 3) & (usable.RelationshipSatisfaction_P2 <= 3)])
    return {"happy": rng.sample(happy, n_happy), "unhappy": rng.sample(unhappy, n_unhappy)}


def setup(couple: int, data: pd.DataFrame | None = None):
    """A couples pool as the Garden's PoolSetup: her real partner is the answer key."""
    from .engine_types import Twin
    from .pools import PoolSetup

    pool = load_pool(load() if data is None else data, couple)
    twins = (Twin(pool.woman.alias, "f"), *(Twin(m.alias, "m") for m in pool.men))
    personas = {p.alias: p.persona_text() for p in (pool.woman, *pool.men)}
    profiles = {p.alias: [{"text": m, "about": "personality"} for m in p.memories] for p in (pool.woman, *pool.men)}
    return PoolSetup(twins, personas, pool.woman.alias, [m.alias for m in pool.men], frozenset({pool.partner}),
                     profiles), pool
