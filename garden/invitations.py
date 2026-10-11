"""Invitations: how two twins can choose each other without acting on the same day.

Asking someone to leave, or heading for the wall alone, opens an invitation to that twin for a few
days, and the invited twin hears about it. If the invited twin then chooses the wall with the inviter
while it is open, both have chosen each other: a breakout. (The F2 ablation found twins did head for
the wall, but never on the same day as the twin they chose, so no breakout could ever happen.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine_types import Action
from .verdict import GATED_RUNGS

WINDOW = 2  # days an invitation stays open after the day it was made


@dataclass
class Invitations:
    _open: dict[tuple[str, str], int] = field(default_factory=dict)  # (inviter, invitee) -> last open day

    def invite(self, inviter: str, invitee: str, day: int) -> None:
        """The inviter's latest choice wins: inviting someone withdraws their earlier invitations."""
        for key in [k for k in self._open if k[0] == inviter and k[1] != invitee]:
            del self._open[key]
        self._open[(inviter, invitee)] = day + WINDOW

    def is_open(self, inviter: str, invitee: str, day: int) -> bool:
        last = self._open.get((inviter, invitee))
        return last is not None and last >= day

    def on_action(self, who: str, action: Action, day: int) -> None:
        """A proposal to leave or a lone wall attempt opens an invitation at once, so it can be answered
        the same day (in the same conversation) or within WINDOW days."""
        if action.rung in GATED_RUNGS and action.target:
            self.invite(who, action.target, day)

    def inviters_of(self, invitee: str, day: int) -> tuple[str, ...]:
        return tuple(sorted(a for (a, b), last in self._open.items() if b == invitee and last >= day))
