"""Scoring: for each man, how often her twin broke out with him when he had the chance.

A man's chance is a run where he had a date with her (or broke out with her anyway): a run that ended
before he ever met her says nothing about him. Only her willingness counts: his twin's choice only
decides whether a run ends in a breakout at all. Excluded runs are never scored. The confidence range is
a 95% Wilson interval on that rate, which behaves sensibly with the handful of runs a demo has.

(Until #65 the first sort key was the highest price level she still broke out at; price levels made no
difference in live runs, so they were removed.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .batch import RunRecord

Z95 = 1.96


@dataclass(frozen=True)
class CandidateScore:
    candidate: str
    breakouts: int   # runs where her twin broke out with him
    runs: int        # scorable runs where he had the chance (a date with her)
    ci_low: float
    ci_high: float

    @property
    def rate(self) -> float:
        return self.breakouts / self.runs if self.runs else 0.0


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; (0, 1) when there is no data."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def strength(c: CandidateScore) -> tuple[float, float]:
    """How strongly her twin chose him: the range's low end (so a steady 9/10 beats a lucky 1/1), then
    the rate itself."""
    return (c.ci_low, round(c.rate, 6))


def _broke_out_with(record: RunRecord, woman: str, man: str) -> bool:
    pair = record.result.pair
    return bool(pair) and set(pair) == {woman, man}


def score(records: list[RunRecord], woman: str, candidates: list[str]) -> list[CandidateScore]:
    """Ranked best first: the low end of the confidence range, then the rate, then name."""
    scorable = [r for r in records if r.result is not None and r.result.scorable]
    scores = []
    for man in candidates:
        chances = [r for r in scorable if r.result.had_date(woman, man) or _broke_out_with(r, woman, man)]
        k = sum(1 for r in chances if _broke_out_with(r, woman, man))
        low, high = wilson(k, len(chances))
        scores.append(CandidateScore(man, k, len(chances), low, high))
    return sorted(scores, key=lambda s: (tuple(-x for x in strength(s)), s.candidate))
