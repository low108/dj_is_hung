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
    schedule: str = ""  # the Coordinator's word: current assignment and tonight's gathering


class OutcomeKind(str, Enum):
    BREAKOUT = "breakout"
    TIMEOUT = "timeout"


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
    """Something the Coordinator announced, for logs and the viewer."""

    day: int
    text: str
