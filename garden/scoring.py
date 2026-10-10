"""Scoring: for each man, the highest price level at which her twin still breaks out with him.

Only her willingness counts: his twin's choice only decides whether a run ends in a breakout at all.
Excluded runs are never scored. The confidence range is a 95% Wilson interval on the breakout rate at
the scored price level, which behaves sensibly with the handful of runs a demo has.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .batch import PriceLevel, RunRecord

PRICE_ORDER = list(PriceLevel)  # low -> high
Z95 = 1.96


@dataclass(frozen=True)
class CandidateScore:
    candidate: str
    price: PriceLevel | None           # highest price level with a breakout together; None = never
    breakouts: int                     # at that price level
    runs: int                          # scorable runs at that price level (or all prices if never)
    ci_low: float
    ci_high: float
    breakouts_by_price: dict[str, tuple[int, int]]  # price -> (breakouts with him, scorable runs)

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


def strength(c: CandidateScore) -> tuple[int, float]:
    """How strongly her twin chose him: price level reached (0 = never), then the range's low end."""
    return (PRICE_ORDER.index(c.price) + 1 if c.price else 0, c.ci_low)


def score(records: list[RunRecord], woman: str, candidates: list[str]) -> list[CandidateScore]:
    """Ranked best first: higher price level, then the low end of the confidence range (so a steady
    9/10 beats a lucky 1/1), then name."""
    scorable = [r for r in records if r.result is not None and r.result.scorable]
    scores = []
    for man in candidates:
        by_price: dict[str, tuple[int, int]] = {}
        for price in PRICE_ORDER:
            runs = [r for r in scorable if r.spec.price is price]
            together = sum(1 for r in runs if r.result.pair and set(r.result.pair) == {woman, man})
            by_price[price.value] = (together, len(runs))
        best = next((p for p in reversed(PRICE_ORDER) if by_price[p.value][0] > 0), None)
        if best is None:  # never broke out with him: the range covers every scored run, at any price
            k, n = 0, len(scorable)
        else:
            k, n = by_price[best.value]
        low, high = wilson(k, n)
        scores.append(CandidateScore(man, best, k, n, low, high, by_price))
    return sorted(scores, key=lambda s: (tuple(-x for x in strength(s)), s.candidate))
