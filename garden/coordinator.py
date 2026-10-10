"""The Coordinator: assigns partners and durations, separates twins who bond, holds gatherings,
and places every action somewhere in the Garden. Rule-based and seeded, so runs are reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from .engine_types import Action, Rung, Twin

PLACES = ("home", "cafe", "park", "gathering_hall", "coordinator_office", "the_wall")
PLACE_WORDS = {"home": "home", "cafe": "the café", "park": "the park", "gathering_hall": "the gathering hall",
               "coordinator_office": "the Coordinator's office", "the_wall": "the wall"}

BONDED = 2.0               # bond at which the Coordinator moves to separate a pair
SHORT, LONG = (1, 2), (3, 4)
GATHERING_RATE = 0.3


@dataclass
class Assignment:
    a: str
    b: str
    days_left: int

    def partner_of(self, who: str) -> str | None:
        return self.b if who == self.a else self.a if who == self.b else None


@dataclass
class Coordinator:
    twins: tuple[Twin, ...]
    rng: Random
    assignments: list[Assignment] = field(default_factory=list)
    announcements: list[tuple[int, str]] = field(default_factory=list)
    gathering_today: bool = False

    # --- daily schedule -------------------------------------------------------------------
    def start_day(self, day: int, bond: dict[str, dict[str, float]]) -> None:
        """Expire finished assignments, separate bonded pairs, pair up the unassigned."""
        for asg in list(self.assignments):
            if asg.days_left <= 0:
                self.assignments.remove(asg)
                self.announcements.append((day, f"{asg.a} and {asg.b}: your time together has ended."))
            elif bond.get(asg.a, {}).get(asg.b, 0) >= BONDED and asg.days_left > SHORT[1]:
                asg.days_left = self.rng.randint(*SHORT)  # bonded: cut it short
                self.announcements.append((day, f"{asg.a} and {asg.b}: {asg.days_left} more day(s)."))
        self._pair_unassigned(day, bond)
        self.gathering_today = self.rng.random() < GATHERING_RATE
        if self.gathering_today:
            self.announcements.append((day, "Tonight there is a gathering at the hall. Everyone attends."))

    def end_day(self) -> None:
        for asg in self.assignments:
            asg.days_left -= 1

    def _pair_unassigned(self, day: int, bond: dict[str, dict[str, float]]) -> None:
        free = [t for t in self.twins if self.partner_of(t.alias) is None]
        self.rng.shuffle(free)
        while free:
            twin = free.pop()
            options = [o for o in free if _compatible(twin, o)]
            if not options:
                continue
            # Prefer whoever this twin is LEAST bonded with: the Coordinator keeps bonded people apart.
            self.rng.shuffle(options)
            other = min(options, key=lambda o: bond.get(twin.alias, {}).get(o.alias, 0.0))
            free.remove(other)
            bonded = bond.get(twin.alias, {}).get(other.alias, 0.0) >= BONDED
            days = self.rng.randint(*(SHORT if bonded else LONG))
            self.assignments.append(Assignment(twin.alias, other.alias, days))
            self.announcements.append((day, f"{twin.alias} and {other.alias}: paired for {days} day(s)."))

    # --- queries ----------------------------------------------------------------------------
    def assignment_of(self, who: str) -> Assignment | None:
        return next((a for a in self.assignments if a.partner_of(who)), None)

    def partner_of(self, who: str) -> str | None:
        asg = self.assignment_of(who)
        return asg.partner_of(who) if asg else None

    def partner_pairs(self) -> set[frozenset[str]]:
        return {frozenset((a.a, a.b)) for a in self.assignments}

    def describe(self, who: str) -> str:
        asg = self.assignment_of(who)
        text = (f"The Coordinator has paired you with {asg.partner_of(who)} "
                f"for {'one more day' if asg.days_left <= 1 else f'{asg.days_left} more days'}."
                if asg else "You are between assignments.")
        if self.gathering_today:
            text += " Tonight there is a gathering at the hall."
        return text

    # --- actions -------------------------------------------------------------------------------
    def on_action(self, day: int, who: str, action: Action) -> None:
        if action.rung is Rung.CHECK_DEVICE and (asg := self.assignment_of(who)):
            asg.days_left = self.rng.randint(1, LONG[1])  # checking early changes things
            self.announcements.append((day, f"{asg.a} and {asg.b}: your time has been changed."))

    def place_for(self, who: str, action: Action, placed: dict[str, str]) -> str:
        """Where an action happens. Social actions join the target if they've already been placed."""
        rung = action.rung
        if rung is Rung.GO_BEYOND_WALL:
            return "the_wall"
        if rung in (Rung.REFLECT, Rung.CHECK_DEVICE):
            return "home"
        if self.gathering_today and rung in (Rung.TALK, Rung.SEEK_OUT):
            return "gathering_hall"
        if action.target and action.target in placed and placed[action.target] not in ("home", "the_wall"):
            return placed[action.target]
        if rung is Rung.PROPOSE_LEAVING:
            return "park"
        return self.rng.choice(("cafe", "park", "coordinator_office") if rung is Rung.GO_TO else ("cafe", "park"))


def _compatible(a: Twin, b: Twin) -> bool:
    return not a.gender or not b.gender or a.gender != b.gender
