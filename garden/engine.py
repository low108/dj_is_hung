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
from .engine_types import (DAY_ENDERS, LEAVING_RUNGS, SOCIAL_RUNGS, Action, Announcement, Attempt, Breach, Event,
                           OutcomeKind, Reflection, Rung, Situation, Twin, TwinState, compatible)
from .coordinator import Coordinator, Phase
from .invitations import Invitations
from .longing import Longing


MAX_TURNS = 20  # turns per twin per day: a conversation ends sooner when both have stopped


@dataclass(frozen=True)
class WorldConfig:
    twins: tuple[Twin, ...]
    max_days: int = 200  # a safety cap: a run ends when every pair has had its dates (or at a breakout)
    max_turns: int = MAX_TURNS
    seed: int = 0
    standing_start: int = standing_rules.START
    # Ablation switches (F2): turn mechanics off one at a time to see what each one does.
    wall_lock: bool = True         # off: proposing to leave and the wall are offered from day one
    standing_enabled: bool = True  # off: no Standing words, infractions cost nothing
    longing_enabled: bool = True   # off: twins don't hear their longing


MAX_SLIPS_PER_TWIN = 2  # more slips than this from one twin in a run, and the run is flagged for review (#64)


class Model(Protocol):
    """Decides what a twin does next. Real models (Gemini, Gemma, ILMU) and the fake model share this.
    Optional extras the engine reads if present: `after_day(day, events) -> list[Reflection]`,
    `notice(twin, day, text)` (something only that twin learns, at once: what its device shows) and
    `breaks: list[Breach]` (lines the model rejected and re-asked for breaking immersion)."""

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
    wall_opened: int | None = None  # the day proposing to leave and the wall were first offered
    breach: Breach | None = None  # the slip that flagged the run (see `flagged`)
    immersion_breaks: list[Breach] = field(default_factory=list)  # rejected and re-asked by the model
    slips: list[Breach] = field(default_factory=list)  # still out of character after re-asking: dropped (#64)
    dated: list[tuple[str, str]] = field(default_factory=list)  # every pair sent on at least one date

    def had_date(self, a: str, b: str) -> bool:
        return tuple(sorted((a, b))) in self.dated

    @property
    def immersion_resamples(self) -> int:
        return len(self.immersion_breaks)

    @property
    def flagged(self) -> bool:
        """A twin kept slipping out of character: the run is kept, but reviewed rather than scored."""
        return self.breach is not None

    @property
    def scorable(self) -> bool:
        return self.outcome is not OutcomeKind.EXCLUDED and not self.flagged


FeedHook = Callable[[Event | Announcement, str], None]
StateHook = Callable[[list[TwinState]], None]


def run_world(config: WorldConfig, model: Model, on_feed: FeedHook | None = None,
              on_state: StateHook | None = None) -> RunResult:
    """Run one world. `on_feed(item, standing_word)` is called for every twin action and every Coordinator
    announcement the moment it happens; `on_state(states)` with every twin's state after each evening.
    The viewer uses both; neither changes the run."""
    rng = Random(config.seed)
    events: list[Event] = []
    unrequited: list[Attempt] = []
    standing = {t.alias: config.standing_start for t in config.twins}
    longing = Longing()
    reflections: list[Reflection] = []
    coordinator = Coordinator(config.twins, Random(config.seed + 1))
    # The wall lock (#63, replacing the verdict gate, #66): nobody can propose leaving or go to the wall
    # until every possible pair has had a date. It opens at the gathering after the last first date, with
    # everyone present, so no one man is with her the moment it opens. Then it's each twin's own choice.
    wall_opened: int | None = None if config.wall_lock else 1
    invitations = Invitations()
    slips: list[Breach] = []  # text that slipped out of character: dropped, the turn kept to itself
    meet = getattr(model, "meet", None)
    if meet:  # models with memory get to know every twin before day one (idle twins reflect too)
        meet(config.twins, config.standing_enabled)

    def result(outcome: OutcomeKind, day: int, pair=None) -> RunResult:
        return RunResult(outcome=outcome, day=day, pair=pair, unrequited=unrequited, events=events,
                         standing=standing, longing={t.alias: longing.of(t.alias) for t in config.twins},
                         reflections=reflections, announcements=coordinator.announcements,
                         wall_opened=wall_opened, breach=repeated_slipper(), slips=slips,
                         immersion_breaks=list(getattr(model, "breaks", [])),
                         dated=sorted(tuple(sorted(p)) for p in coordinator.dates))

    def twin_states(day: int, reflected: dict[str, str]) -> list[TwinState]:
        out = []
        for t in config.twins:
            pair = coordinator.assignment_of(t.alias)
            out.append(TwinState(
                day=day, twin=t.alias,
                partner=pair.partner_of(t.alias) if pair else None,
                days_left=max(pair.days_left, 0) if pair else None,
                standing=word_for(t.alias),
                longing_hearts=longing.hearts(t.alias) if config.longing_enabled else {},
                reflection=reflected.get(t.alias, "")))  # a reflection that slipped is already dropped
        return out

    def emit_states(day: int, reflected: dict[str, str] | None = None) -> None:
        if on_state:
            on_state(twin_states(day, reflected or {}))

    def repeated_slipper() -> Breach | None:
        """The slip that took a twin past MAX_SLIPS_PER_TWIN, if any."""
        counts: dict[str, int] = {}
        for s in slips:
            counts[s.twin] = counts.get(s.twin, 0) + 1
            if counts[s.twin] > MAX_SLIPS_PER_TWIN:
                return s
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

    def targets_for(twin: Twin, phase: Phase) -> tuple[str, ...]:
        """Who a twin can act toward today: its partner on a date, anyone it could be paired with at a
        gathering. (Talking needs them still around; going to the wall for them doesn't, see play_day.)"""
        if phase is Phase.DATE:
            partner = coordinator.partner_of(twin.alias)
            return (partner,) if partner else ()
        if phase is Phase.GATHERING:
            return tuple(o.alias for o in config.twins if o != twin and compatible(twin, o))
        return ()

    def play_day(day: int) -> tuple[tuple[str, str] | None, dict[str, str], list[tuple[str, Action]]]:
        """Today's turns. Only twins on a date or at the gathering act. A twin keeps acting until it does
        something on its own (which ends its day) or uses its MAX_TURNS; the twin just spoken to answers
        next, otherwise whoever's turn comes up at random. Returns (breakout, wall crossings, actions)."""
        by_alias = {t.alias: t for t in config.twins}
        active = [t for t in config.twins if coordinator.phase_of(t.alias) is not Phase.IDLE]
        turns = {t.alias: 0 for t in active}
        done: set[str] = set()
        crossings: dict[str, str] = {}
        todays: list[tuple[str, Action]] = []
        placed: dict[str, str] = {}
        answering: str | None = None
        spoken: set[str] = set()  # on a date: who has said something to their partner today
        unanswered: dict[str, tuple[str, str]] = {}  # twin -> (speaker, line) said to it, not yet answered
        hear = getattr(model, "hear", None)
        notice = getattr(model, "notice", None)
        while True:
            ready = [t for t in active if t.alias not in done and turns[t.alias] < config.max_turns]
            if not ready:
                return None, crossings, todays
            twin = by_alias[answering] if answering in {t.alias for t in ready} else rng.choice(ready)
            turns[twin.alias] += 1
            phase = coordinator.phase_of(twin.alias)
            targets = targets_for(twin, phase)
            wall_open = wall_opened is not None
            partner = coordinator.partner_of(twin.alias) if phase is Phase.DATE else None
            # A date day opens with a conversation: neither can withdraw until both have spoken (unless
            # the partner has already gone for the day).
            must_talk = bool(partner) and partner not in done and not {twin.alias, partner} <= spoken
            replying_to = unanswered.pop(twin.alias, None)  # one chance to answer: its next turn
            situation = Situation(
                standing=standing_rules.describe(standing[twin.alias]) if config.standing_enabled else "",
                longing=longing.describe(twin.alias) if config.longing_enabled else "",
                schedule=coordinator.describe(twin.alias),
                wall_open=wall_open,
                standing_in_play=config.standing_enabled,
                invited_by=invitations.inviters_of(twin.alias, day) if wall_open else (),
                phase=phase.value, targets=targets, must_talk=must_talk, replying_to=replying_to)
            action = model.choose_action(twin, day, tuple(by_alias[a] for a in targets), situation)
            if action.rung in LEAVING_RUNGS and not wall_open:
                action = Action(Rung.REFLECT)  # the lock holds for every model, not just well-behaved ones
            elif action.rung in SOCIAL_RUNGS and (action.target not in targets or (
                    action.rung is not Rung.GO_BEYOND_WALL and action.target in done)):
                # Out of reach (or gone for the day, unless it's the wall, a private choice that doesn't
                # need them there): it keeps to itself instead.
                action = Action(Rung.REFLECT)
            elif action.rung is Rung.SEEK_OUT and phase is Phase.DATE:
                action = Action(Rung.TALK, action.target, action.say)  # on a date they're already together
            if must_talk and action.rung not in SOCIAL_RUNGS:
                action = Action(Rung.TALK, partner, action.say)  # not yet: they haven't both spoken
            if phrase := immersion.breaking_phrase(action.say):
                # Out of character (#64): nobody hears it, and the twin keeps to itself this turn instead.
                slips.append(Breach(day, twin.alias, phrase, action.say))
                action = Action(Rung.REFLECT)
            if partner and action.rung in SOCIAL_RUNGS and action.target == partner:
                spoken.add(twin.alias)
            todays.append((twin.alias, action))
            coordinator.on_action(day, twin.alias, action)
            if notice and action.rung is Rung.CHECK_DEVICE:  # it sees the (re-rolled) time left at once
                notice(twin.alias, day, coordinator.device_reading(twin.alias))
            invitations.on_action(twin.alias, action, day)
            before = standing[twin.alias]
            if config.standing_enabled:
                standing[twin.alias] = standing_rules.charge(before, action.rung)
            placed[twin.alias] = coordinator.place_for(twin.alias, action, placed)
            event = Event(day, twin.alias, action.rung, action.target, action.say, before,
                          standing[twin.alias], placed[twin.alias])
            events.append(event)
            stream(event, word_for(twin.alias))
            if hear:
                hear(event)  # whoever was spoken to hears it now, mid-conversation
            if action.say and action.target and action.rung in SOCIAL_RUNGS and action.rung is not Rung.GO_BEYOND_WALL:
                unanswered[action.target] = (twin.alias, action.say)  # the wall is private: nothing to answer
            answering = action.target if action.rung in SOCIAL_RUNGS else None
            if action.rung in DAY_ENDERS:
                done.add(twin.alias)
            if action.rung is Rung.GO_BEYOND_WALL:
                # A breakout needs both to choose each other: both at the wall for each other today, or
                # answering an invitation the other made (today or within the last few days).
                crossings[twin.alias] = action.target
                other = action.target
                if crossings.get(other) == twin.alias or invitations.is_open(other, twin.alias, day):
                    return tuple(sorted((twin.alias, other))), {}, todays

    for day in range(1, config.max_days + 1):
        coordinator.start_day(day, longing.bond)
        if wall_opened is None and coordinator.everyone_met():
            wall_opened = day
            coordinator.open_wall(day)
        stream()
        breakout, crossings, todays_actions = play_day(day)

        if breakout:  # crossing the wall together costs everything
            for i, e in enumerate(events):
                if e.day == day and e.twin in breakout:
                    standing[e.twin] = 0
                    events[i] = replace(e, standing_after=0)

        todays_events = [e for e in events if e.day == day]
        if breakout:
            emit_states(day)  # the last evening: the pair's Standing is gone
            return result(OutcomeKind.BREAKOUT, day, breakout)
        unrequited += [Attempt(day, a, b) for a, b in crossings.items()]
        if config.standing_enabled:  # a day without infractions earns a little back, up to the start
            infringed = {who for who, a in todays_actions if a.rung in standing_rules.COST}
            for t in config.twins:
                if t.alias not in infringed:
                    standing[t.alias] = standing_rules.compliant_day(standing[t.alias], config.standing_start)
        longing.end_of_day(todays_actions, coordinator.partner_pairs())
        coordinator.end_day()

        after_day = getattr(model, "after_day", None)  # models with memory hear what happened today
        todays = (after_day(day, todays_events) or []) if after_day else []
        for i, r in enumerate(todays):
            if phrase := immersion.breaking_phrase(r.text):  # out of character: dropped, not shown (#64)
                slips.append(Breach(day, r.twin, phrase, r.text))
                todays[i] = replace(r, text="")
        emit_states(day, {r.twin: r.text for r in todays})
        reflections.extend(todays)
        if coordinator.rounds_complete():  # every man has had his dates: nobody broke out
            return result(OutcomeKind.TIMEOUT, day)

    return result(OutcomeKind.TIMEOUT, config.max_days)  # the safety cap
