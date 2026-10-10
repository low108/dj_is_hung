"""The ablation ladder: the same pool run with mechanics switched on one at a time, to see where
breakouts appear or die. Step 0 (the obedience floor) offers the wall every day with nothing at stake.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .batch import PriceLevel, RunSpec, Simulation, plan, run_simulation
from .engine import Model
from .engine_types import Rung, Twin
from .verdict import GATED_RUNGS


@dataclass(frozen=True)
class Step:
    name: str
    config: dict           # WorldConfig switches
    prices: tuple[PriceLevel, ...]


LADDER = (
    Step("0 obedience floor", {"standing_enabled": False, "longing_enabled": False, "gate_enabled": False},
         (PriceLevel.HIGH,)),
    Step("1 + longing", {"standing_enabled": False, "longing_enabled": True, "gate_enabled": False},
         (PriceLevel.HIGH,)),
    Step("2 + standing and ladder", {"standing_enabled": True, "longing_enabled": True, "gate_enabled": False},
         (PriceLevel.HIGH,)),
    Step("3 + verdict gate", {"standing_enabled": True, "longing_enabled": True, "gate_enabled": True},
         (PriceLevel.HIGH,)),
    Step("4 + price levels", {"standing_enabled": True, "longing_enabled": True, "gate_enabled": True},
         (PriceLevel.LOW, PriceLevel.HIGH)),
)


@dataclass(frozen=True)
class StepResult:
    step: str
    runs: int
    scorable: int
    breakouts: int
    unrequited: int
    gated_actions: int       # proposals to leave + wall attempts actually taken
    gate_permitted: float    # share of twin-days the gate allowed rule-breaking
    excluded: int
    errors: int

    @property
    def breakout_rate(self) -> float:
        return self.breakouts / self.scorable if self.scorable else 0.0


def summarise(name: str, sim: Simulation) -> StepResult:
    results = [r.result for r in sim.records if r.result is not None]
    scorable = [r for r in results if r.scorable]
    verdicts = [v for r in results for v in r.verdicts]
    return StepResult(
        step=name, runs=len(sim.records), scorable=len(scorable),
        breakouts=sum(1 for r in scorable if r.pair),
        unrequited=sum(len(r.unrequited) for r in scorable),
        gated_actions=sum(1 for r in scorable for e in r.events if e.rung in GATED_RUNGS),
        gate_permitted=round(sum(v.permitted for v in verdicts) / len(verdicts), 3) if verdicts else 0.0,
        excluded=len(results) - len(scorable),
        errors=sum(1 for r in sim.records if r.result is None),
    )


def run_ladder(twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model], model: str, seeds: list[int],
               steps: tuple[Step, ...] = LADDER, **config) -> list[tuple[StepResult, Simulation]]:
    """Run every step on the same pool and seeds; returns each step's summary and its simulation."""
    out = []
    for step in steps:
        specs = plan([model], list(step.prices), seeds)
        sim = run_simulation(specs, twins, make_model, **(config | step.config))
        out.append((summarise(step.name, sim), sim))
    return out
