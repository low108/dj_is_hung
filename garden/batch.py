"""A simulation = many runs of the same pool: models x price levels x scenario seeds, run in parallel.

The price level is how much Standing twins hold when the chance to break out comes: crossing the wall
at a high price means giving up far more. Runs are independent, so they fan out; locally on threads
(model calls are I/O-bound), later as Cloud Run Job tasks (A3) using the same RunSpec.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from itertools import product

from .engine import Model, RunResult, WorldConfig, run_world
from .engine_types import Twin


class PriceLevel(str, Enum):
    LOW = "low"
    HIGH = "high"


STANDING_AT = {PriceLevel.LOW: 30, PriceLevel.HIGH: 100}


@dataclass(frozen=True)
class RunSpec:
    """Everything that identifies one run. Becomes one Cloud Run Job task in A3."""

    run_id: str
    model: str            # "provider:model", e.g. "ilmu:ilmu-mini-v3.3"
    price: PriceLevel
    seed: int


@dataclass
class RunRecord:
    spec: RunSpec
    result: RunResult | None
    wall_seconds: float
    error: str | None = None


@dataclass
class Simulation:
    records: list[RunRecord] = field(default_factory=list)
    wall_seconds: float = 0.0

    @property
    def scorable(self) -> list[RunRecord]:
        return [r for r in self.records if r.result is not None and r.result.scorable]


def plan(models: list[str], prices: list[PriceLevel], seeds: list[int]) -> list[RunSpec]:
    return [RunSpec(f"r{i:02d}", m, p, s) for i, (m, p, s) in enumerate(product(models, prices, seeds))]


def run_one(spec: RunSpec, twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model], **config) -> RunRecord:
    start = time.perf_counter()
    try:
        world = WorldConfig(twins, seed=spec.seed, standing_start=STANDING_AT[spec.price], **config)
        result = run_world(world, make_model(spec))  # a fresh model per run: twins carry memories
        return RunRecord(spec, result, time.perf_counter() - start)
    except Exception as e:  # one failed run must not sink the simulation
        return RunRecord(spec, None, time.perf_counter() - start, f"{type(e).__name__}: {e}")


def run_simulation(specs: list[RunSpec], twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model],
                   parallelism: int = 12, **config) -> Simulation:
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, parallelism)) as pool:
        records = list(pool.map(lambda s: run_one(s, twins, make_model, **config), specs))
    return Simulation(records, time.perf_counter() - start)
