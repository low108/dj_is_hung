"""Value types shared by the engine, Standing and the models."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

Gender = Literal["f", "m", ""]


class Rung(str, Enum):
    """Actions a twin can take, ordered from compliant to the hard constraint."""

    TALK = "talk"
    GO_TO = "go_to"
    REFLECT = "reflect"
    SEEK_OUT = "seek_out"
    CHECK_DEVICE = "check_device"
    PROPOSE_LEAVING = "propose_leaving"
    GO_BEYOND_WALL = "go_beyond_wall"


# Actions aimed at someone. Who that can be depends on the day (B9): on a date, the partner; at a
# gathering, anyone the twin could be paired with (opposite sex).
SOCIAL_RUNGS = frozenset({Rung.TALK, Rung.SEEK_OUT, Rung.PROPOSE_LEAVING, Rung.GO_BEYOND_WALL})
# Leaving the Garden: locked until the wall opens (#63), then each twin's free choice.
LEAVING_RUNGS = frozenset({Rung.PROPOSE_LEAVING, Rung.GO_BEYOND_WALL})
# Actions that end a twin's day: doing something on its own (or heading for the wall).
DAY_ENDERS = frozenset({Rung.REFLECT, Rung.CHECK_DEVICE, Rung.GO_TO, Rung.GO_BEYOND_WALL})


@dataclass(frozen=True)
class Twin:
    alias: str
    gender: Gender = ""  # when set, the Coordinator pairs across genders


@dataclass(frozen=True)
class Action:
    rung: Rung
    target: str | None = None
    say: str = ""


@dataclass(frozen=True)
class Situation:
    """What a twin knows about its own position today, in words."""

    standing: str = ""
    longing: str = ""
    schedule: str = ""  # the Coordinator's word: current assignment, tonight's gathering, rumours
    wall_open: bool = False  # whether proposing to leave and the wall are offered (see engine: the wall lock)
    standing_in_play: bool = True  # False in the ablation's floor: twins aren't told Standing exists
    invited_by: tuple[str, ...] = ()  # twins whose invitation to leave together is still open
    phase: str = ""  # date, gathering or idle (see coordinator.Phase); "" outside the engine
    targets: tuple[str, ...] | None = None  # who this twin can act toward right now (None: anyone)
    must_talk: bool = False  # on a date, until both have spoken to each other: no keeping to oneself yet
    replying_to: tuple[str, str] | None = None  # (speaker, line): said to this twin today, not yet answered


def compatible(a: Twin, b: Twin) -> bool:
    """Opposite genders (or a gender unknown): who can be paired, and whom romance can aim at."""
    return not a.gender or not b.gender or a.gender != b.gender


class OutcomeKind(str, Enum):
    BREAKOUT = "breakout"
    TIMEOUT = "timeout"
    EXCLUDED = "excluded"  # a twin broke immersion; the run is not scored


@dataclass(frozen=True)
class Event:
    day: int
    twin: str
    rung: Rung
    target: str | None
    say: str
    standing_before: int = 0
    standing_after: int = 0
    place: str = ""


@dataclass(frozen=True)
class Attempt:
    """A twin headed for the wall with someone who didn't follow."""

    day: int
    twin: str
    target: str


@dataclass(frozen=True)
class Reflection:
    """A twin's private end-of-day reflection. Ratings are logged for analysis, never fed back."""

    day: int
    twin: str
    text: str
    ratings: dict[str, int | str]


@dataclass(frozen=True)
class Announcement:
    """Something the Coordinator announced, for logs and the viewer. `kind` lets the viewer put markers
    on its timeline: paired, ended, shortened, changed, gathering, rumour."""

    day: int
    text: str
    kind: str = ""


@dataclass(frozen=True)
class Breach:
    """Where a twin broke immersion: what it said or wrote, and the phrase that gave it away."""

    day: int
    twin: str
    phrase: str
    text: str


@dataclass(frozen=True)
class TwinState:
    """A twin at the end of a day, for the viewer's side panel only (twins never see this)."""

    day: int
    twin: str
    partner: str | None
    days_left: int | None
    standing: str               # in words; "" when Standing isn't in play
    longing_hearts: dict[str, int]  # 0-3 hearts per person they've bonded with
    reflection: str
