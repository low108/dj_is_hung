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

from .engine import FeedHook, Model, RunResult, StateHook, WorldConfig, run_world
from .engine_types import Twin


class PriceLevel(str, Enum):
    """How much a twin would give up by crossing the wall. Twins start with this much Standing and
    build it up by keeping to the rules, so a high price means Pairing Day is close."""

    LOW = "low"
    HIGH = "high"

    @property
    def standing(self) -> int:
        return {PriceLevel.LOW: 20, PriceLevel.HIGH: 90}[self]


@dataclass(frozen=True)
class RunSpec:
    """Everything that identifies one run. Becomes one Cloud Run Job task in A3."""

    run_id: str
    model: str            # "provider:model", e.g. "ilmu:ilmu-mini-v3.3"
    price: PriceLevel
    seed: int


@dataclass(frozen=True)
class RunRecord:
    spec: RunSpec
    result: RunResult | None
    wall_seconds: float
    error: str | None = None

    @property
    def scorable(self) -> bool:
        return self.result is not None and self.result.scorable


@dataclass
class Simulation:
    records: list[RunRecord] = field(default_factory=list)
    wall_seconds: float = 0.0

    @property
    def scorable(self) -> list[RunRecord]:
        return [r for r in self.records if r.scorable]


def plan(models: list[str], prices: list[PriceLevel], seeds: list[int]) -> list[RunSpec]:
    """Every combination of model, price level and seed, in a fixed order (task index -> RunSpec)."""
    return [RunSpec(f"r{i:02d}", m, p, s) for i, (m, p, s) in enumerate(product(models, prices, seeds))]


def featured_spec(specs: list[RunSpec]) -> RunSpec | None:
    """The run shown live: the first high-price run (the most at stake), else the first run."""
    return next((s for s in specs if s.price is PriceLevel.HIGH), specs[0] if specs else None)


@dataclass(frozen=True)
class Observer:
    """What listens to a run as it happens (the replay recorder, which also feeds the live viewer)."""

    on_feed: FeedHook | None = None
    on_state: StateHook | None = None


def run_one(spec: RunSpec, twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model],
            observer: Observer | None = None, **config) -> RunRecord:
    """One run; extra keyword arguments go to WorldConfig (e.g. max_days, thresholds)."""
    start = time.perf_counter()
    try:
        world = WorldConfig(twins, seed=spec.seed, standing_start=spec.price.standing, **config)
        hooks = observer or Observer()
        result = run_world(world, make_model(spec), hooks.on_feed, hooks.on_state)  # a fresh model per run
        return RunRecord(spec, result, time.perf_counter() - start)
    except Exception as e:  # one failed run must not sink the simulation
        return RunRecord(spec, None, time.perf_counter() - start, f"{type(e).__name__}: {e}")


def run_simulation(specs: list[RunSpec], twins: tuple[Twin, ...], make_model: Callable[[RunSpec], Model],
                   parallelism: int = 12, observe: Callable[[RunSpec], Observer | None] | None = None,
                   on_finished: Callable[[RunRecord], None] | None = None, **config) -> Simulation:
    """`observe(spec)` gives each run's Observer (or None); `on_finished(record)` is called as each run
    ends, on that run's thread, so its replay is saved even if a later run never finishes."""
    start = time.perf_counter()

    def go(spec: RunSpec) -> RunRecord:
        record = run_one(spec, twins, make_model, observe(spec) if observe else None, **config)
        if on_finished:
            on_finished(record)
        return record

    with ThreadPoolExecutor(max_workers=max(1, parallelism)) as pool:
        records = list(pool.map(go, specs))
    return Simulation(records, time.perf_counter() - start)
