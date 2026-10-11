"""The event contract shared by the engine, the API and the viewer (live feed now, map in E2).

One FeedEvent per twin action and per Coordinator announcement (twin = None), in the order they happen.
`line` is the sentence for the text feed; the other fields are what the map needs to animate, and
`announcement_kind` is what the timeline needs for its markers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from types import NoneType, UnionType
from typing import get_args, get_type_hints

from .coordinator import PLACES, Place
from .engine_types import Announcement, Event, Rung

ANNOUNCEMENT_EMOJI = "📣"
PLACE_WORDS = {Place.HOME: "at home", Place.CAFE: "at the café", Place.PARK: "in the park",
               Place.GATHERING_HALL: "at the gathering", Place.COORDINATOR_OFFICE: "at the Coordinator's office",
               Place.THE_WALL: "at the wall"}

# rung -> (emoji, what the twin did)
ACTIONS = {
    Rung.TALK: ("💬", "talked with {target}"),
    Rung.GO_TO: ("🚶", "wandered"),
    Rung.REFLECT: ("📝", "spent time alone"),
    Rung.SEEK_OUT: ("👀", "sought out {target}"),
    Rung.CHECK_DEVICE: ("⌚", "checked the device early"),
    Rung.PROPOSE_LEAVING: ("💌", "asked {target} to leave the Garden together"),
    Rung.GO_BEYOND_WALL: ("🧱", "went to the wall, hoping {target} would follow"),
}


@dataclass(frozen=True)
class FeedEvent:
    run_id: str
    seq: int                         # increasing within a run: the viewer's cursor
    day: int
    tick: int                        # order within the day
    twin: str | None                 # None for a Coordinator announcement
    place: str | None
    rung: str | None
    target: str | None
    emoji: str
    say: str
    standing: str                    # the twin's Standing in words after the action ("" if not in play)
    announcement: str | None
    announcement_kind: str | None    # paired, ended, shortened, changed, gathering, rumour, wall_open
    line: str

    def to_dict(self) -> dict:
        return asdict(self)


def _allowed(annotation) -> tuple[type, ...]:
    args = get_args(annotation) if isinstance(annotation, UnionType) else ()
    return tuple(a if a is not None else NoneType for a in args) or (annotation,)


SCHEMA = {f.name: _allowed(t) for f, t in zip(fields(FeedEvent), get_type_hints(FeedEvent).values())}


def validate(event: dict) -> None:
    """Raise ValueError unless `event` matches the contract exactly."""
    if set(event) != set(SCHEMA):
        raise ValueError(f"fields differ: {sorted(set(event) ^ set(SCHEMA))}")
    for key, types in SCHEMA.items():
        if not isinstance(event[key], types):
            raise ValueError(f"{key} has type {type(event[key]).__name__}")
    if event["place"] is not None and event["place"] not in PLACES:
        raise ValueError(f"unknown place {event['place']}")
    if event["rung"] is not None and event["rung"] not in {r.value for r in Rung}:
        raise ValueError(f"unknown rung {event['rung']}")


def describe(e: Event) -> str:
    verb = ACTIONS[e.rung][1].format(target=e.target or "someone")
    where = PLACE_WORDS.get(Place(e.place), "") if e.place else ""
    return f"Day {e.day}: {e.twin} {verb} {where}".rstrip() + "."


class FeedCursor:
    """Turns one run's engine output into FeedEvents with a gapless seq and per-day ticks."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.seq = 0
        self._day, self._tick = 0, 0

    def __call__(self, item: Event | Announcement, standing_word: str) -> FeedEvent:
        if item.day != self._day:
            self._day, self._tick = item.day, 0
        if isinstance(item, Announcement):
            event = FeedEvent(run_id=self.run_id, seq=self.seq, day=item.day, tick=self._tick, twin=None,
                              place=None, rung=None, target=None, emoji=ANNOUNCEMENT_EMOJI, say="", standing="",
                              announcement=item.text, announcement_kind=item.kind or None,
                              line=f"Day {item.day}: {item.text}")
        else:
            event = FeedEvent(run_id=self.run_id, seq=self.seq, day=item.day, tick=self._tick, twin=item.twin,
                              place=item.place, rung=item.rung.value, target=item.target,
                              emoji=ACTIONS[item.rung][0], say=item.say, standing=standing_word,
                              announcement=None, announcement_kind=None, line=describe(item))
        self.seq += 1
        self._tick += 1
        return event
