"""Cross-model agreement (F4): does each model, on its own runs, reach the same verdict on a candidate
as the whole ensemble? A candidate's verdict is the highest price level at which her twin broke out
with him (see scoring), so agreement is the number of models whose own verdict matches.

Models with no scored runs (every run errored or was excluded) have no verdict and aren't counted.
"""
from __future__ import annotations

from dataclasses import dataclass

from .batch import RunRecord
from .scoring import CandidateScore, score


@dataclass(frozen=True)
class Agreement:
    candidate: str
    verdict: str | None              # the ensemble's: highest price level with a breakout (None = never)
    by_model: dict[str, str | None]  # each model's own verdict
    agree: int                       # models whose verdict matches the ensemble's
    models: int                      # models with scored runs

    def to_dict(self) -> dict:
        return {"candidate": self.candidate, "verdict": self.verdict, "by_model": self.by_model,
                "agree": self.agree, "models": self.models}


def _level(c: CandidateScore) -> str | None:
    return c.price.value if c.price else None


def agreement(records: list[RunRecord], ensemble: list[CandidateScore], woman: str,
              men: list[str]) -> list[Agreement]:
    """One row per candidate, in the ensemble's ranking order."""
    scored_models = sorted({r.spec.model for r in records if r.result is not None and r.result.scorable})
    verdicts = {m: {c.candidate: _level(c) for c in score([r for r in records if r.spec.model == m], woman, men)}
                for m in scored_models}
    rows = []
    for c in ensemble:
        by_model = {m: verdicts[m][c.candidate] for m in scored_models}
        agree = sum(1 for v in by_model.values() if v == _level(c))
        rows.append(Agreement(c.candidate, _level(c), by_model, agree, len(scored_models)))
    return rows
