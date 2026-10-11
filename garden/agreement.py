"""Cross-model agreement (F4): for each candidate, does each model, on its own runs, reach the same
verdict as the other models together? A candidate's verdict is whether her twin chose him (tried to
leave with him) in any of those runs (see scoring). Comparing a model with the *others* (not the full pool, which
includes its own runs) keeps one model from agreeing with itself.

Every model that ran is listed; one with no scored runs (all errored or excluded) has no verdict, shows
as "no data" and can't agree, so a failed model is visible rather than silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass

from .batch import RunRecord
from .scoring import CandidateScore, score

NO_DATA = "no data"
CHOSE = "chose him"


@dataclass(frozen=True)
class Agreement:
    candidate: str
    verdict: str | None              # the whole ensemble's: CHOSE, or None (never)
    by_model: dict[str, str | None]  # each model's own verdict, or NO_DATA
    agree: int                       # models whose verdict matches the other models' pooled verdict
    models: int                      # every model that ran

    def to_dict(self) -> dict:
        return {"candidate": self.candidate, "verdict": self.verdict, "by_model": self.by_model,
                "agree": self.agree, "models": self.models}


def _level(c: CandidateScore) -> str | None:
    return CHOSE if c.chosen else None


def _verdicts(records: list[RunRecord], woman: str, men: list[str]) -> dict[str, str | None]:
    return {c.candidate: _level(c) for c in score(records, woman, men)}


def agreement(records: list[RunRecord], ensemble: list[CandidateScore], woman: str,
              men: list[str]) -> list[Agreement]:
    """One row per candidate, in the ensemble's ranking order."""
    models = sorted({r.spec.model for r in records})
    scored = {m for m in models if any(r.scorable for r in records if r.spec.model == m)}
    own = {m: _verdicts([r for r in records if r.spec.model == m], woman, men) for m in scored}
    others = {m: _verdicts([r for r in records if r.spec.model != m], woman, men) for m in scored}
    rows = []
    for c in ensemble:
        by_model = {m: own[m][c.candidate] if m in scored else NO_DATA for m in models}
        # A model agrees when the others have scored runs too and reach the same verdict.
        agree = sum(1 for m in scored if len(scored) > 1 and own[m][c.candidate] == others[m][c.candidate])
        rows.append(Agreement(c.candidate, _level(c), by_model, agree, len(models)))
    return rows
