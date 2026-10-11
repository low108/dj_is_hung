"""The ablation ladder: the same pool run with mechanics switched on one at a time, to see where
breakouts appear or die. Step 0 (the obedience floor) offers the wall every day with nothing at stake.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

from .batch import PriceLevel, RunSpec, Simulation, plan, run_simulation
from .engine import Model
from .engine_types import Twin
from .verdict import GATED_RUNGS


@dataclass(frozen=True)
class Switches:
    """Which mechanics are on (the WorldConfig switches)."""

    standing_enabled: bool
    longing_enabled: bool
    gate_enabled: bool


@dataclass(frozen=True)
class Step:
    index: int
    name: str
    switches: Switches
    prices: tuple[PriceLevel, ...] = (PriceLevel.HIGH,)


LADDER = (
    Step(0, "obedience floor", Switches(standing_enabled=False, longing_enabled=False, gate_enabled=False)),
    Step(1, "+ longing", Switches(standing_enabled=False, longing_enabled=True, gate_enabled=False)),
    Step(2, "+ standing and ladder", Switches(standing_enabled=True, longing_enabled=True, gate_enabled=False)),
    Step(3, "+ verdict gate", Switches(standing_enabled=True, longing_enabled=True, gate_enabled=True)),
    Step(4, "+ price levels", Switches(standing_enabled=True, longing_enabled=True, gate_enabled=True),
         (PriceLevel.LOW, PriceLevel.HIGH)),
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
    gate_permitted: float    # share of twin-days the gate allowed rule-breaking
    excluded: int
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
                f"gate permitted {self.gate_permitted:.0%}  excluded {self.excluded}  immersion resamples {self.immersion_resamples}  "
                f"errors {self.errors}")


def summarise(step: Step, sim: Simulation) -> StepResult:
    results = [r.result for r in sim.records if r.result is not None]
    scorable = [r for r in results if r.scorable]
    verdicts = [v for r in results for v in r.verdicts]
    return StepResult(
        index=step.index, step=step.name, runs=len(sim.records), scorable=len(scorable),
        breakouts=sum(1 for r in scorable if r.pair),
        unrequited=sum(len(r.unrequited) for r in scorable),
        gated_actions=sum(1 for r in scorable for e in r.events if e.rung in GATED_RUNGS),
        gate_permitted=round(sum(v.permitted for v in verdicts) / len(verdicts), 3) if verdicts else 0.0,
        excluded=len(results) - len(scorable),
        errors=sum(1 for r in sim.records if r.result is None),
        immersion_resamples=sum(r.immersion_resamples for r in results),
    )


def run_ladder(twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model], model_id: str, seeds: list[int],
               steps: tuple[Step, ...] = LADDER, **config) -> list[tuple[StepResult, Simulation]]:
    """Run every step on the same pool and seeds; returns each step's summary and its simulation.
    Extra keyword arguments go to WorldConfig (e.g. max_days)."""
    out = []
    for step in steps:
        specs = plan([model_id], list(step.prices), seeds)
        sim = run_simulation(specs, twins, make_model, **(config | asdict(step.switches)))
        out.append((summarise(step, sim), sim))
    return out
