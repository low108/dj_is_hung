"""The Garden simulation: twins act day by day until two of them cross the wall together.

Seam: `run_world(config, model) -> RunResult`. Models decide actions; the engine owns the rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Protocol

from . import standing as standing_rules
from .engine_types import Action, Announcement, Attempt, Event, OutcomeKind, Reflection, Rung, Situation, Twin
from .coordinator import Coordinator
from .longing import Longing


@dataclass(frozen=True)
class WorldConfig:
    twins: tuple[Twin, ...]
    max_days: int = 10
    seed: int = 0
    standing_start: int = standing_rules.START


class Model(Protocol):
    """Decides what a twin does next. Real models (Gemini, Gemma, ILMU) and the fake model share this."""

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...], situation: Situation) -> Action: ...


@dataclass
class RunResult:
    outcome: OutcomeKind
    day: int
    pair: tuple[str, str] | None = None
    unrequited: list[Attempt] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    standing: dict[str, int] = field(default_factory=dict)  # at the end of the run
    longing: dict[str, dict[str, float]] = field(default_factory=dict)  # at the end of the run
    reflections: list[Reflection] = field(default_factory=list)
    announcements: list[Announcement] = field(default_factory=list)  # Coordinator, for the viewer


def run_world(config: WorldConfig, model: Model) -> RunResult:
    rng = Random(config.seed)
    events: list[Event] = []
    unrequited: list[Attempt] = []
    standing = {t.alias: config.standing_start for t in config.twins}
    longing = Longing()
    reflections: list[Reflection] = []
    coordinator = Coordinator(config.twins, Random(config.seed + 1))

    def result(outcome: OutcomeKind, day: int, pair=None) -> RunResult:
        return RunResult(outcome, day, pair, unrequited, events, standing,
                         {t.alias: longing.of(t.alias) for t in config.twins}, reflections,
                         coordinator.announcements)

    for day in range(1, config.max_days + 1):
        coordinator.start_day(day, longing.bond)
        order = list(config.twins)
        rng.shuffle(order)  # nobody gets to act first every day
        crossings: dict[str, str] = {}
        actions: dict[str, Action] = {}
        for twin in order:
            others = tuple(t for t in config.twins if t != twin)
            situation = Situation(standing=standing_rules.describe(standing[twin.alias]),
                                  longing=longing.describe(twin.alias),
                                  schedule=coordinator.describe(twin.alias))
            actions[twin.alias] = action = model.choose_action(twin, day, others, situation)
            coordinator.on_action(day, twin.alias, action)
            if action.rung is Rung.GO_BEYOND_WALL and action.target:
                crossings[twin.alias] = action.target

        # Decisions are private and simultaneous: a breakout needs both to choose each other.
        breakout = next((tuple(sorted((a, b))) for a, b in crossings.items() if crossings.get(b) == a), None)

        placed: dict[str, str] = {}
        for twin in order:
            action, before = actions[twin.alias], standing[twin.alias]
            crossed = breakout is not None and twin.alias in breakout
            standing[twin.alias] = 0 if crossed else standing_rules.after(before, action.rung)
            placed[twin.alias] = coordinator.place_for(twin.alias, action, placed)
            events.append(Event(day, twin.alias, action.rung, action.target, action.say, before,
                                standing[twin.alias], placed[twin.alias]))

        if breakout:
            return result(OutcomeKind.BREAKOUT, day, breakout)
        unrequited += [Attempt(day, a, b) for a, b in crossings.items()]
        longing.end_of_day(actions, coordinator.partner_pairs())
        coordinator.end_day()

        after_day = getattr(model, "after_day", None)  # models with memory hear what happened today
        if after_day:
            reflections.extend(after_day(day, [e for e in events if e.day == day]) or [])

    return result(OutcomeKind.TIMEOUT, config.max_days)
