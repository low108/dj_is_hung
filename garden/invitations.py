"""Invitations: how two twins can choose each other without acting on the same day.

Asking someone to leave, or heading for the wall alone, opens an invitation to that twin, and the
invited twin hears about it. It stays open until it is answered or the inviter invites someone else:
in live runs a 2-day window expired before the invited man had a turn again (after the wall opens a man
acts only on his date or at a gathering), so mutual choices days apart never met. If the invited twin
then asks the inviter to leave, or goes to the wall with them, both have chosen each other: a breakout.
(The F2 ablation found twins did head for the wall, but never on the same day as the twin they chose,
so no breakout could ever happen.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine_types import LEAVING_RUNGS, Action

@dataclass
class Invitations:
    _open: dict[tuple[str, str], int] = field(default_factory=dict)  # (inviter, invitee) -> day made

    def invite(self, inviter: str, invitee: str, day: int) -> None:
        """The inviter's latest choice wins: inviting someone withdraws their earlier invitations."""
        for key in [k for k in self._open if k[0] == inviter and k[1] != invitee]:
            del self._open[key]
        self._open[(inviter, invitee)] = day

    def is_open(self, inviter: str, invitee: str, day: int) -> bool:
        made = self._open.get((inviter, invitee))
        return made is not None and made <= day

    def on_action(self, who: str, action: Action, day: int) -> None:
        """A proposal to leave or a lone wall attempt opens an invitation at once, so it can be answered
        the same day (in the same conversation) or any day after, until the inviter invites someone else."""
        if action.rung in LEAVING_RUNGS and action.target:
            self.invite(who, action.target, day)

    def inviters_of(self, invitee: str, day: int) -> tuple[str, ...]:
        return tuple(sorted(a for (a, b), made in self._open.items() if b == invitee and made <= day))
