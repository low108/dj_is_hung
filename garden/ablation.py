"""The ablation ladder: the same pool run with mechanics switched on one at a time, to see where
breakouts appear or die. Step 0 (the obedience floor) offers the wall every day with nothing at stake;
the last step adds the wall lock (no leaving until every pair has had a date, #63).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

from .batch import RunSpec, Simulation, plan, run_simulation
from .engine import Model
from .engine_types import LEAVING_RUNGS, Twin


@dataclass(frozen=True)
class Switches:
    """Which mechanics are on (the WorldConfig switches)."""

    standing_enabled: bool
    longing_enabled: bool
    wall_lock: bool


@dataclass(frozen=True)
class Step:
    index: int
    name: str
    switches: Switches


LADDER = (
    Step(0, "obedience floor", Switches(standing_enabled=False, longing_enabled=False, wall_lock=False)),
    Step(1, "+ longing", Switches(standing_enabled=False, longing_enabled=True, wall_lock=False)),
    Step(2, "+ standing and ladder", Switches(standing_enabled=True, longing_enabled=True, wall_lock=False)),
    Step(3, "+ wall lock", Switches(standing_enabled=True, longing_enabled=True, wall_lock=True)),
)


@dataclass(frozen=True)
class StepResult:
    index: int
    step: str
    runs: int
    scorable: int
    breakouts: int
    unrequited: int
    gated_actions: int       # proposals to leave + wall attempts actually taken
    wall_opened: float       # share of scored runs where the wall opened
    flagged: int             # a twin kept slipping out of character: not scored
    errors: int
    immersion_resamples: int = 0  # lines re-asked because they broke immersion

    @property
    def breakout_rate(self) -> float:
        return self.breakouts / self.scorable if self.scorable else 0.0

    def as_row(self) -> dict:
        return asdict(self) | {"breakout_rate": round(self.breakout_rate, 3)}

    def describe(self) -> str:
        return (f"{self.index} {self.step:22s} runs {self.runs:2d}  breakouts {self.breakouts}/{self.scorable} "
                f"({self.breakout_rate:.0%})  unrequited {self.unrequited:2d}  gated actions {self.gated_actions:3d}  "
                f"wall opened {self.wall_opened:.0%}  flagged {self.flagged}  immersion resamples {self.immersion_resamples}  "
                f"errors {self.errors}")


def summarise(step: Step, sim: Simulation) -> StepResult:
    results = [r.result for r in sim.records if r.result is not None]
    scorable = [r for r in results if r.scorable]
    return StepResult(
        index=step.index, step=step.name, runs=len(sim.records), scorable=len(scorable),
        breakouts=sum(1 for r in scorable if r.pair),
        unrequited=sum(len(r.unrequited) for r in scorable),
        gated_actions=sum(1 for r in scorable for e in r.events if e.rung in LEAVING_RUNGS),
        wall_opened=round(sum(r.wall_opened is not None for r in scorable) / len(scorable), 3) if scorable else 0.0,
        flagged=len(results) - len(scorable),
        errors=sum(1 for r in sim.records if r.result is None),
        immersion_resamples=sum(r.immersion_resamples for r in results),
    )


def run_ladder(twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model], model_id: str, seeds: list[int],
               steps: tuple[Step, ...] = LADDER, **config) -> list[tuple[StepResult, Simulation]]:
    """Run every step on the same pool and seeds; returns each step's summary and its simulation.
    Extra keyword arguments go to WorldConfig (e.g. max_days)."""
    out = []
    for step in steps:
        specs = plan([model_id], seeds)
        sim = run_simulation(specs, twins, make_model, **(config | asdict(step.switches)))
        out.append((summarise(step, sim), sim))
    return out
