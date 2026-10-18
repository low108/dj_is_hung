"""The Coordinator: sends twins on dates, separates twins who bond, holds a gathering after every date,
and places every action somewhere in the Garden. Rule-based and seeded, so runs are reproducible.

The rhythm (B9): a date (a pair assigned for a few days; only they act, toward each other), then a
gathering day when the date ends (everyone acts, toward anyone they could be paired with), then the
next date. Least-dated pairs go first, so every man gets his dates; a run lasts until every possible
pair has had DATES_EACH dates (see `rounds_complete`).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from random import Random

from .engine_types import Action, Announcement, Rung, Twin, compatible

Bonds = dict[str, dict[str, float]]


class Place(str, Enum):
    HOME = "home"
    CAFE = "cafe"
    PARK = "park"
    GATHERING_HALL = "gathering_hall"
    COORDINATOR_OFFICE = "coordinator_office"
    THE_WALL = "the_wall"


PLACES = tuple(p.value for p in Place)

BONDED = 2.0               # bond at which the Coordinator moves to keep a pair apart
SHORT, LONG = (1, 2), (3, 4)
RESHUFFLE = (1, 4)         # checking the device early re-rolls the time left within this range
DATES_EACH = 2             # a run lasts until every possible pair has had this many dates
RUMOUR_RATE = 0.5          # talk of leaving "may be noticed"
RUMOUR = "People whisper that someone spoke of leaving the Garden."
# What twins hear about their schedule (Coordinator announcements are logs, not twin-facing).
SCHEDULE_PAIRED = "You are on a date with {partner}, assigned by the Coordinator for {time_left}."
SCHEDULE_ONE_DAY, SCHEDULE_DAYS = "one more day", "{days} more days"
SCHEDULE_UNASSIGNED = "You are between assignments today and keep to yourself."
SCHEDULE_GATHERING = "Today everyone gathers at the hall."
# What the device shows the twin who checks it, at once (it also re-rolls the date's length, see on_action).
DEVICE_READING = "I checked my Coordinator device early. It says my time with {partner} {time_left}."
DEVICE_LAST_DAY, DEVICE_DAYS = "ends tonight", "has {days} more days"
DEVICE_NO_DATE = "I checked my Coordinator device early. It shows no one assigned to me right now."


class Phase(str, Enum):
    """What a twin's day is: who it can act with, and whether it acts at all."""

    DATE = "date"            # with its assigned partner only
    GATHERING = "gathering"  # with anyone it could be paired with
    IDLE = "idle"            # no turns: someone else is on a date


def bond_between(bonds: Bonds, x: str, y: str) -> float:
    """Bonds are symmetric in practice; take the stronger side so one twin's view is enough."""
    return max(bonds.get(x, {}).get(y, 0.0), bonds.get(y, {}).get(x, 0.0))


@dataclass
class Assignment:
    first: str
    second: str
    days_left: int

    def partner_of(self, who: str) -> str | None:
        if who == self.first:
            return self.second
        if who == self.second:
            return self.first
        return None

    @property
    def names(self) -> str:
        return f"{self.first} and {self.second}"


@dataclass
class Coordinator:
    twins: tuple[Twin, ...]
    rng: Random
    assignments: list[Assignment] = field(default_factory=list)
    announcements: list[Announcement] = field(default_factory=list)
    gathering_today: bool = False
    rumour_today: bool = False
    _rumour_tomorrow: bool = False
    _bonds: Bonds = field(default_factory=dict)
    dates: Counter = field(default_factory=Counter)  # frozenset({a, b}) -> dates they've been sent on

    def _announce(self, day: int, kind: str, text: str) -> None:
        self.announcements.append(Announcement(day, text, kind))

    # --- daily schedule -------------------------------------------------------------------
    def start_day(self, day: int, bonds: Bonds) -> None:
        """End finished dates (a date that ends makes today a gathering), cut bonded pairs short, and on
        an ordinary day send the unassigned on their next dates."""
        self._bonds = bonds
        self.gathering_today = False
        for pair in list(self.assignments):
            if pair.days_left <= 0:
                self.assignments.remove(pair)
                self._announce(day, "ended", f"{pair.names}: your time together has ended.")
                self.gathering_today = True
            elif self._bonded(pair.first, pair.second) and pair.days_left > SHORT[1]:
                pair.days_left = self.rng.randint(*SHORT)
                self._announce(day, "shortened", f"{pair.names}: {pair.days_left} more day(s).")
        if self.gathering_today:
            self._announce(day, "gathering", "The date is over. Today everyone gathers at the hall.")
        else:
            self._pair_unassigned(day)
        self.rumour_today, self._rumour_tomorrow = self._rumour_tomorrow, False
        if self.rumour_today:
            self._announce(day, "rumour", RUMOUR)

    def end_day(self) -> None:
        if self.gathering_today:  # dates pause while everyone is at the hall
            return
        for pair in self.assignments:
            pair.days_left -= 1

    def phase_of(self, who: str) -> Phase:
        if self.gathering_today:
            return Phase.GATHERING
        return Phase.DATE if self.assignment_of(who) else Phase.IDLE

    def everyone_met(self) -> bool:
        """Every pair that could be sent on a date has had one, and none is still on its first."""
        pairs = self._possible_pairs()
        running_first = any(self.dates[frozenset((p.first, p.second))] <= 1 for p in self.assignments)
        return bool(pairs) and not running_first and all(self.dates[p] >= 1 for p in pairs)

    def pairing_day(self, day: int) -> None:
        self._announce(day, "pairing_day", "Pairing Day: everyone stayed, and the Coordinator pairs each of "
                       "them with their partner for life.")

    def open_wall(self, day: int) -> None:
        self._announce(day, "wall_open", "Everyone has had a date with everyone they could be paired with.")

    def _possible_pairs(self) -> list[frozenset[str]]:
        return [frozenset((a.alias, b.alias)) for i, a in enumerate(self.twins) for b in self.twins[i + 1:]
                if compatible(a, b)]

    def rounds_complete(self) -> bool:
        """Every pair that could be sent on a date has had DATES_EACH (and none is still on one)."""
        pairs = self._possible_pairs()
        return bool(pairs) and not self.assignments and all(self.dates[p] >= DATES_EACH for p in pairs)

    def _bonded(self, x: str, y: str) -> bool:
        return bond_between(self._bonds, x, y) >= BONDED

    def _pair_unassigned(self, day: int) -> None:
        """Choose pairs globally: fewest dates together first (so everyone gets their dates), then
        least bonded, so a bonded pair is only re-paired when there is no one else."""
        free = [t for t in self.twins if self.partner_of(t.alias) is None]
        candidates = [(a, b) for i, a in enumerate(free) for b in free[i + 1:] if compatible(a, b)]
        self.rng.shuffle(candidates)  # random tie-break: who goes first varies per run
        candidates.sort(key=lambda ab: (self.dates[frozenset((ab[0].alias, ab[1].alias))],
                                        bond_between(self._bonds, ab[0].alias, ab[1].alias)))
        taken: set[str] = set()
        for a, b in candidates:
            if a.alias in taken or b.alias in taken:
                continue
            taken |= {a.alias, b.alias}
            days = self.rng.randint(*(SHORT if self._bonded(a.alias, b.alias) else LONG))
            self.assignments.append(Assignment(a.alias, b.alias, days))
            self.dates[frozenset((a.alias, b.alias))] += 1
            self._announce(day, "paired", f"{a.alias} and {b.alias}: paired for {days} day(s).")

    # --- queries ----------------------------------------------------------------------------
    def assignment_of(self, who: str) -> Assignment | None:
        return next((p for p in self.assignments if p.partner_of(who)), None)

    def partner_of(self, who: str) -> str | None:
        pair = self.assignment_of(who)
        return pair.partner_of(who) if pair else None

    def partner_pairs(self) -> set[frozenset[str]]:
        return {frozenset((p.first, p.second)) for p in self.assignments}

    def device_reading(self, who: str) -> str:
        """What a twin sees when it checks its device: its date's time left (after any re-roll)."""
        pair = self.assignment_of(who)
        if not pair:
            return DEVICE_NO_DATE
        time_left = DEVICE_LAST_DAY if pair.days_left <= 1 else DEVICE_DAYS.format(days=pair.days_left)
        return DEVICE_READING.format(partner=pair.partner_of(who), time_left=time_left)

    def describe(self, who: str) -> str:
        """A twin's day in words: its date, the gathering, or a day to itself."""
        pair = self.assignment_of(who)
        if self.gathering_today:
            text = SCHEDULE_GATHERING
        elif pair:
            time_left = SCHEDULE_ONE_DAY if pair.days_left <= 1 else SCHEDULE_DAYS.format(days=pair.days_left)
            text = SCHEDULE_PAIRED.format(partner=pair.partner_of(who), time_left=time_left)
        else:
            text = SCHEDULE_UNASSIGNED
        if self.rumour_today:
            text += " " + RUMOUR
        return text

    # --- actions -------------------------------------------------------------------------------
    def on_action(self, day: int, who: str, action: Action) -> None:
        if action.rung in (Rung.PROPOSE_LEAVING, Rung.GO_BEYOND_WALL) and self.rng.random() < RUMOUR_RATE:
            self._rumour_tomorrow = True  # noticed: everyone hears a rumour tomorrow
        if action.rung is Rung.CHECK_DEVICE and (pair := self.assignment_of(who)):
            # Checking early changes things, but never lets a bonded pair stay together longer.
            span = SHORT if self._bonded(pair.first, pair.second) else RESHUFFLE
            pair.days_left = self.rng.randint(*span)
            self._announce(day, "changed", f"{pair.names}: your time has been changed.")

    def place_for(self, who: str, action: Action, placed: dict[str, str]) -> str:
        """Where an action happens. On a gathering day everyone is at the hall (unless at the wall);
        otherwise social actions join the target if the target has already been placed."""
        rung = action.rung
        if rung is Rung.GO_BEYOND_WALL:
            return Place.THE_WALL.value
        if self.gathering_today:
            return Place.GATHERING_HALL.value
        if rung in (Rung.REFLECT, Rung.CHECK_DEVICE):
            return Place.HOME.value
        target_place = placed.get(action.target or "")
        if target_place and target_place not in (Place.HOME.value, Place.THE_WALL.value):
            return target_place
        if rung is Rung.PROPOSE_LEAVING:
            return Place.PARK.value
        options = (Place.CAFE, Place.PARK, Place.COORDINATOR_OFFICE) if rung is Rung.GO_TO else (Place.CAFE, Place.PARK)
        return self.rng.choice(options).value
