"""The Garden simulation: twins act day by day until two of them cross the wall together.

Seam: `run_world(config, model) -> RunResult`. Models decide actions; the engine owns the rules.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from random import Random
from typing import Protocol

from . import immersion
from . import standing as standing_rules
from . import verdict as verdict_rules
from .engine_types import (Action, Announcement, Attempt, Breach, Event, OutcomeKind, Reflection, Rung,
                           Situation, Twin, Verdict)
from .coordinator import Coordinator
from .invitations import Invitations
from .longing import Longing


@dataclass(frozen=True)
class WorldConfig:
    twins: tuple[Twin, ...]
    max_days: int = 10
    seed: int = 0
    standing_start: int = standing_rules.START
    thresholds: tuple[tuple[str, float], ...] = ()  # per-twin rebelliousness thresholds (alias, value)
    default_threshold: float = verdict_rules.DEFAULT_THRESHOLD
    # Ablation switches (F2): turn mechanics off one at a time to see what each one does.
    gate_enabled: bool = True      # off: proposing to leave and the wall are always offered
    standing_enabled: bool = True  # off: no Standing words, infractions cost nothing
    longing_enabled: bool = True   # off: twins don't hear their longing

    def threshold_for(self, alias: str) -> float:
        return dict(self.thresholds).get(alias, self.default_threshold)


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
    verdicts: list[Verdict] = field(default_factory=list)  # one per twin per day
    breach: Breach | None = None  # set when the run was excluded
    resamples: int = 0  # lines/reflections the model re-asked because they broke immersion

    @property
    def scorable(self) -> bool:
        return self.outcome is not OutcomeKind.EXCLUDED


FeedHook = Callable[[Event | Announcement, str], None]


def run_world(config: WorldConfig, model: Model, on_feed: FeedHook | None = None) -> RunResult:
    """Run one world. `on_feed(item, standing_word)` is called for every twin action and every Coordinator
    announcement the moment it happens (the live feed uses it); it never changes the run."""
    rng = Random(config.seed)
    events: list[Event] = []
    unrequited: list[Attempt] = []
    standing = {t.alias: config.standing_start for t in config.twins}
    longing = Longing()
    reflections: list[Reflection] = []
    coordinator = Coordinator(config.twins, Random(config.seed + 1))
    verdicts: list[Verdict] = []
    last_ratings: dict[str, dict] = {}  # each twin's own latest reflection ratings: the verdict's assessment
    invitations = Invitations()

    def result(outcome: OutcomeKind, day: int, pair=None, breach: Breach | None = None) -> RunResult:
        return RunResult(outcome=outcome, day=day, pair=pair, unrequited=unrequited, events=events,
                         standing=standing, longing={t.alias: longing.of(t.alias) for t in config.twins},
                         reflections=reflections, announcements=coordinator.announcements,
                         verdicts=verdicts, breach=breach, resamples=getattr(model, "resamples", 0))

    def find_breach(day: int, writings: list[tuple[str, str]]) -> Breach | None:
        for twin, text in writings:
            if phrase := immersion.breaking_phrase(text):
                return Breach(day, twin, phrase, text)
        return None

    emitted = 0  # announcements already streamed

    def stream(item: Event | None = None, word: str = "") -> None:
        """Stream an action (if any), then every announcement not yet streamed, which includes any the
        action just caused, so announcements always follow what caused them."""
        nonlocal emitted
        if not on_feed:
            return
        if item is not None:
            on_feed(item, word)
        for a in coordinator.announcements[emitted:]:
            on_feed(a, "")
        emitted = len(coordinator.announcements)

    def word_for(alias: str) -> str:
        return standing_rules.describe(standing[alias]) if config.standing_enabled else ""

    for day in range(1, config.max_days + 1):
        coordinator.start_day(day, longing.bond)
        stream()
        order = list(config.twins)
        rng.shuffle(order)  # nobody gets to act first every day
        crossings: dict[str, str] = {}
        actions: dict[str, Action] = {}
        placed: dict[str, str] = {}
        for twin in order:
            others = tuple(t for t in config.twins if t != twin)
            verdict = verdict_rules.decide(day, twin.alias, last_ratings.get(twin.alias, {}),
                                           config.threshold_for(twin.alias), config.gate_enabled)
            verdicts.append(verdict)
            situation = Situation(
                standing=standing_rules.describe(standing[twin.alias]) if config.standing_enabled else "",
                longing=longing.describe(twin.alias) if config.longing_enabled else "",
                schedule=coordinator.describe(twin.alias),
                may_break_rules=verdict.permitted,
                standing_in_play=config.standing_enabled,
                # only told when they could answer: a closed gate can't accept an invitation
                invited_by=invitations.inviters_of(twin.alias, day) if verdict.permitted else ())
            action = model.choose_action(twin, day, others, situation)
            if action.rung in verdict_rules.GATED_RUNGS and not verdict.permitted:
                action = Action(Rung.REFLECT)  # the gate holds for every model, not just well-behaved ones
            actions[twin.alias] = action
            coordinator.on_action(day, twin.alias, action)
            if action.rung is Rung.GO_BEYOND_WALL and action.target:
                crossings[twin.alias] = action.target
            before = standing[twin.alias]
            if config.standing_enabled:
                standing[twin.alias] = standing_rules.after(before, action.rung)
            placed[twin.alias] = coordinator.place_for(twin.alias, action, placed)
            event = Event(day, twin.alias, action.rung, action.target, action.say, before,
                          standing[twin.alias], placed[twin.alias])
            events.append(event)
            # speech that breaks immersion ends the run as excluded; don't put it on screen
            shown = event if not immersion.breaking_phrase(action.say) else replace(event, say="")
            stream(shown, word_for(twin.alias))

        # A breakout needs both to choose each other: on the same day (decided privately), or by answering
        # an invitation the other made on an earlier day that is still open.
        breakout = next((tuple(sorted((a, b))) for a, b in crossings.items()
                         if crossings.get(b) == a or invitations.is_open(b, a, day)), None)

        if breakout:  # crossing the wall together costs everything
            for i, e in enumerate(events):
                if e.day == day and e.twin in breakout:
                    standing[e.twin] = 0
                    events[i] = replace(e, standing_after=0)

        todays_events = [e for e in events if e.day == day]
        if found := find_breach(day, [(e.twin, e.say) for e in todays_events]):
            return result(OutcomeKind.EXCLUDED, day, breach=found)  # checked first: a broken run proves nothing
        if breakout:
            return result(OutcomeKind.BREAKOUT, day, breakout)
        unrequited += [Attempt(day, a, b) for a, b in crossings.items()]
        invitations.end_of_day(day, actions)
        longing.end_of_day(actions, coordinator.partner_pairs())
        coordinator.end_day()

        after_day = getattr(model, "after_day", None)  # models with memory hear what happened today
        if after_day:
            todays = after_day(day, todays_events) or []
            reflections.extend(todays)
            last_ratings.update({r.twin: r.ratings for r in todays if r.ratings})
            if found := find_breach(day, [(r.twin, r.text) for r in todays]):
                return result(OutcomeKind.EXCLUDED, day, breach=found)

    return result(OutcomeKind.TIMEOUT, config.max_days)
