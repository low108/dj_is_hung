"""Longing: a per-person pull that grows while apart from someone you bonded with.

Kept as numbers inside the engine; twins only ever hear it in words. Until the Coordinator
assigns partners (B4), "together today" means the two twins interacted today.
"""
from __future__ import annotations

from collections import defaultdict

from .engine_types import Action, Rung

BONDING = {Rung.TALK, Rung.SEEK_OUT, Rung.PROPOSE_LEAVING}
BOND_PER_DAY = 1.0
BOND_CAP = 5.0
RISE_PER_BOND = 0.6   # longing added per day apart, per unit of bond
FALL_TOGETHER = 2.0   # longing removed on a day together
DECAY = 0.9           # everything fades a little each day


class Longing:
    def __init__(self) -> None:
        self.bond: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.level: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def end_of_day(self, actions: dict[str, Action]) -> None:
        together: set[frozenset[str]] = {
            frozenset((who, a.target)) for who, a in actions.items() if a.rung in BONDING and a.target
        }
        for pair in together:
            a, b = tuple(pair)
            for x, y in ((a, b), (b, a)):
                self.bond[x][y] = min(BOND_CAP, self.bond[x][y] + BOND_PER_DAY)

        for x, bonds in self.bond.items():
            for y, bond in bonds.items():
                if frozenset((x, y)) in together:
                    self.level[x][y] = max(0.0, self.level[x][y] - FALL_TOGETHER)
                else:
                    self.level[x][y] += RISE_PER_BOND * bond
                self.level[x][y] *= DECAY

    def of(self, who: str) -> dict[str, float]:
        return dict(self.level.get(who, {}))

    def describe(self, who: str) -> str:
        """How a twin feels its strongest longing. No numbers, ever."""
        levels = self.of(who)
        if not levels:
            return ""
        name, value = max(levels.items(), key=lambda kv: kv[1])
        if value >= 6:
            return f"You miss {name} badly."
        if value >= 3:
            return f"You keep thinking about {name}."
        if value >= 1:
            return f"You wonder how {name} is doing."
        return ""
