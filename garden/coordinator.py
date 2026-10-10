"""The Coordinator: assigns partners and durations, separates twins who bond, holds gatherings,
and places every action somewhere in the Garden. Rule-based and seeded, so runs are reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from random import Random

from .engine_types import Action, Announcement, Rung, Twin

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
GATHERING_RATE = 0.3
RUMOUR_RATE = 0.5          # talk of leaving "may be noticed"
RUMOUR = "People whisper that someone spoke of leaving the Garden."
# What twins hear about their schedule (Coordinator announcements are logs, not twin-facing).
SCHEDULE_PAIRED = "The Coordinator has paired you with {partner} for {time_left}."
SCHEDULE_ONE_DAY, SCHEDULE_DAYS = "one more day", "{days} more days"
SCHEDULE_UNASSIGNED = "You are between assignments."
SCHEDULE_GATHERING = "Tonight there is a gathering at the hall."


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

    def _announce(self, day: int, text: str) -> None:
        self.announcements.append(Announcement(day, text))

    # --- daily schedule -------------------------------------------------------------------
    def start_day(self, day: int, bonds: Bonds) -> None:
        """Expire finished assignments, cut bonded pairs short, pair up the unassigned."""
        self._bonds = bonds
        for pair in list(self.assignments):
            if pair.days_left <= 0:
                self.assignments.remove(pair)
                self._announce(day, f"{pair.names}: your time together has ended.")
            elif self._bonded(pair.first, pair.second) and pair.days_left > SHORT[1]:
                pair.days_left = self.rng.randint(*SHORT)
                self._announce(day, f"{pair.names}: {pair.days_left} more day(s).")
        self._pair_unassigned(day)
        self.gathering_today = self.rng.random() < GATHERING_RATE
        if self.gathering_today:
            self._announce(day, "Tonight there is a gathering at the hall. Everyone attends.")
        self.rumour_today, self._rumour_tomorrow = self._rumour_tomorrow, False
        if self.rumour_today:
            self._announce(day, RUMOUR)

    def end_day(self) -> None:
        for pair in self.assignments:
            pair.days_left -= 1

    def _bonded(self, x: str, y: str) -> bool:
        return bond_between(self._bonds, x, y) >= BONDED

    def _pair_unassigned(self, day: int) -> None:
        """Choose pairs globally, least-bonded first, so a bonded pair is only re-paired when
        there is no one else. (Choosing per twin let whoever was picked first decide.)"""
        free = [t for t in self.twins if self.partner_of(t.alias) is None]
        candidates = [(a, b) for i, a in enumerate(free) for b in free[i + 1:] if _compatible(a, b)]
        self.rng.shuffle(candidates)  # random tie-break: who goes first varies per run
        candidates.sort(key=lambda ab: bond_between(self._bonds, ab[0].alias, ab[1].alias))
        taken: set[str] = set()
        for a, b in candidates:
            if a.alias in taken or b.alias in taken:
                continue
            taken |= {a.alias, b.alias}
            days = self.rng.randint(*(SHORT if self._bonded(a.alias, b.alias) else LONG))
            self.assignments.append(Assignment(a.alias, b.alias, days))
            self._announce(day, f"{a.alias} and {b.alias}: paired for {days} day(s).")

    # --- queries ----------------------------------------------------------------------------
    def assignment_of(self, who: str) -> Assignment | None:
        return next((p for p in self.assignments if p.partner_of(who)), None)

    def partner_of(self, who: str) -> str | None:
        pair = self.assignment_of(who)
        return pair.partner_of(who) if pair else None

    def partner_pairs(self) -> set[frozenset[str]]:
        return {frozenset((p.first, p.second)) for p in self.assignments}

    def describe(self, who: str) -> str:
        """A twin's schedule in words: its assignment, plus tonight's gathering if there is one."""
        pair = self.assignment_of(who)
        if pair:
            time_left = SCHEDULE_ONE_DAY if pair.days_left <= 1 else SCHEDULE_DAYS.format(days=pair.days_left)
            text = SCHEDULE_PAIRED.format(partner=pair.partner_of(who), time_left=time_left)
        else:
            text = SCHEDULE_UNASSIGNED
        if self.gathering_today:
            text += " " + SCHEDULE_GATHERING
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
            self._announce(day, f"{pair.names}: your time has been changed.")

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


def _compatible(a: Twin, b: Twin) -> bool:
    return not a.gender or not b.gender or a.gender != b.gender
