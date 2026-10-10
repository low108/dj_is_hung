"""Demo pools from the speed-dating data, and the answer-key check.

A pool is one real woman, the men she mutually matched with (the answer key), and a few men she met
who were not mutual matches. If the mechanic works, her real matches should rank above the others.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from random import Random

import pandas as pd

from . import speed_dating as sd
from .engine_types import Twin
from .scoring import CandidateScore, strength


@dataclass(frozen=True)
class Pool:
    woman: sd.TwinRecord
    men: tuple[sd.TwinRecord, ...]
    matched: frozenset[str]  # aliases of the men she mutually matched with: the answer key

    @property
    def twins(self) -> tuple[Twin, ...]:
        return (Twin(self.woman.alias, "f"), *(Twin(m.alias, "m") for m in self.men))

    @property
    def personas(self) -> dict[str, str]:
        return {r.alias: r.persona_text() for r in (self.woman, *self.men)}

    @property
    def men_aliases(self) -> list[str]:
        return [m.alias for m in self.men]


def eligible_women(dates: pd.DataFrame, min_matches: int = 2, min_non_matches: int = 3) -> list[dict]:
    """Women with enough matches and non-matches to make a meaningful pool."""
    women = dates[dates["gender"] == 0]
    stats = women.groupby("iid").agg(wave=("wave", "first"), dates=("pid", "count"), matches=("match", "sum"))
    stats = stats[(stats["matches"] >= min_matches) & (stats["dates"] - stats["matches"] >= min_non_matches)]
    return [{"iid": int(i), "wave": int(r.wave), "dates": int(r.dates), "matches": int(r.matches)}
            for i, r in stats.iterrows()]


def load_pool(dates: pd.DataFrame, iid: int, non_matches: int = 3, max_matches: int | None = None,
              seed: int = 0, model=None) -> Pool:
    """Her twin, all her matched men (or up to `max_matches`) and `non_matches` men she met without a
    mutual match. `model`, if given, rewrites twin memories (see speed_dating.build_twin)."""
    rows = dates[(dates["iid"] == iid) & dates["pid"].notna()]
    if rows.empty or int(rows.iloc[0]["gender"]) != 0:
        raise KeyError(f"{iid} is not a woman in the dataset")
    rng = Random(seed)
    matched_ids = sorted(int(p) for p in rows[rows["match"] == 1]["pid"])
    other_ids = sorted(int(p) for p in rows[rows["match"] == 0]["pid"])
    rng.shuffle(matched_ids)
    rng.shuffle(other_ids)
    chosen_matched, chosen_others = matched_ids[:max_matches], other_ids[:non_matches]

    woman = sd.build_twin(dates, iid, model)
    men, matched, used = [], set(), {woman.alias}
    for pid in sorted(chosen_matched + chosen_others):
        twin = sd.build_twin(dates, pid, model)
        alias = _unique(twin.alias, used)
        men.append(replace(twin, alias=alias))
        used.add(alias)
        if pid in chosen_matched:
            matched.add(alias)
    return Pool(woman, tuple(men), frozenset(matched))


def _unique(alias: str, used: set[str]) -> str:
    n, out = 2, alias
    while out in used:
        out, n = f"{alias} {n}", n + 1
    return out


@dataclass(frozen=True)
class AnswerKeyCheck:
    matched_ranks: dict[str, int]       # her real matches -> rank (1 = top)
    other_ranks: dict[str, int]
    matches_on_top: bool                 # every real match ranked above every non-match
    pairs_in_order: float                # share of (match, non-match) pairs ordered correctly: 0.5 = chance


def check_ranking(scores: list[CandidateScore], matched: frozenset[str]) -> AnswerKeyCheck:
    """The answer-key check for a scorer ranking, comparing the same strength the scorer ranks by."""
    return check_answer_key([c.candidate for c in scores], matched, {c.candidate: strength(c) for c in scores})


def check_answer_key(ranked: list[str], matched: frozenset[str],
                     strength: dict[str, tuple] | None = None) -> AnswerKeyCheck:
    """How well a ranking (best first) recovers her real mutual matches.

    `strength` is each candidate's score key (higher = stronger). Candidates with equal strength are
    tied, whatever order they were listed in, and a tied (match, non-match) pair counts as half right,
    so a ranking with no information scores 0.5 rather than whatever alphabetical order happens to give.
    """
    strength = strength or {n: (-i,) for i, n in enumerate(ranked)}
    rank = {name: i + 1 for i, name in enumerate(ranked)}
    m = {n: rank[n] for n in ranked if n in matched}
    o = {n: rank[n] for n in ranked if n not in matched}
    pairs = [(a, b) for a in m for b in o]
    credit = sum(1.0 if strength[a] > strength[b] else 0.5 if strength[a] == strength[b] else 0.0 for a, b in pairs)
    in_order = credit / len(pairs) if pairs else 0.0
    on_top = bool(pairs) and all(strength[a] > strength[b] for a, b in pairs)
    return AnswerKeyCheck(m, o, on_top, round(in_order, 3))


@dataclass(frozen=True)
class PoolSetup:
    """Everything a simulation needs about who is in the world: the demo pool or a real woman's pool."""

    twins: tuple[Twin, ...]
    personas: dict[str, str]
    woman: str
    men: list[str]
    matched: frozenset[str] | None  # the answer key; None for the demo pool


def resolve(pool_iid: int | None, dates: Callable[[], pd.DataFrame] = sd.load) -> PoolSetup:
    """The demo pool when `pool_iid` is None, otherwise that real woman's pool (KeyError if not a woman)."""
    from . import demo

    if pool_iid is None:
        return PoolSetup(demo.POOL, demo.PERSONAS, demo.WOMAN, demo.MEN, None)
    pool = load_pool(dates(), pool_iid)
    return PoolSetup(pool.twins, pool.personas, pool.woman.alias, pool.men_aliases, pool.matched)
