"""Scoring: for each man, how often her twin chose him when he had the chance.

Her twin chose him in a run when she asked him to leave the Garden with her or went to the wall with
him, whether or not he followed: only her willingness counts. (Scoring only breakouts let his answer
and the schedule decide: in live runs she tried to leave with two to four men in turn, and the first
to say yes took the run.) A man's chance is a run where he had a date with her: a run that ended
before he ever met her says nothing about him. Breakouts are reported alongside. Excluded runs are never scored. The confidence range is
a 95% Wilson interval on that rate, which behaves sensibly with the handful of runs a demo has.

(Until #65 the first sort key was the highest price level she still broke out at; price levels made no
difference in live runs, so they were removed.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .batch import RunRecord
from .engine_types import LEAVING_RUNGS

Z95 = 1.96


@dataclass(frozen=True)
class CandidateScore:
    candidate: str
    chosen: int      # runs where her twin tried to leave with him (asked him, or went to the wall with him)
    runs: int        # scorable runs where he had the chance (a date with her)
    ci_low: float    # 95% range on chosen / runs
    ci_high: float
    breakouts: int = 0  # runs where they actually crossed the wall together

    @property
    def rate(self) -> float:
        return self.chosen / self.runs if self.runs else 0.0


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


def _she_chose(record: RunRecord, woman: str, man: str) -> bool:
    return _broke_out_with(record, woman, man) or any(
        e.twin == woman and e.target == man and e.rung in LEAVING_RUNGS for e in record.result.events)


def score(records: list[RunRecord], woman: str, candidates: list[str]) -> list[CandidateScore]:
    """Ranked best first: the low end of the confidence range, then the rate, then name."""
    scorable = [r for r in records if r.result is not None and r.result.scorable]
    scores = []
    for man in candidates:
        chances = [r for r in scorable if r.result.had_date(woman, man) or _she_chose(r, woman, man)]
        k = sum(1 for r in chances if _she_chose(r, woman, man))
        low, high = wilson(k, len(chances))
        together = sum(1 for r in chances if _broke_out_with(r, woman, man))
        scores.append(CandidateScore(man, k, len(chances), low, high, together))
    return sorted(scores, key=lambda s: (tuple(-x for x in strength(s)), s.candidate))
