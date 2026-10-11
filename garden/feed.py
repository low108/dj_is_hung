"""The event contract shared by the engine, the API and the viewer (live feed now, map in E2).

One FeedEvent per twin action, plus one per Coordinator announcement (twin = None). `line` is the
human-readable sentence for the text feed; the other fields are what the map needs to animate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .coordinator import PLACES
from .engine_types import Announcement, Event, Rung

EMOJI = {
    Rung.TALK: "💬", Rung.GO_TO: "🚶", Rung.REFLECT: "📝", Rung.SEEK_OUT: "👀",
    Rung.CHECK_DEVICE: "⌚", Rung.PROPOSE_LEAVING: "💌", Rung.GO_BEYOND_WALL: "🧱",
}
ANNOUNCEMENT_EMOJI = "📣"

PLACE_WORDS = {"home": "at home", "cafe": "at the café", "park": "in the park",
               "gathering_hall": "at the gathering", "coordinator_office": "at the Coordinator's office",
               "the_wall": "at the wall"}

VERBS = {
    Rung.TALK: "talked with {target}", Rung.GO_TO: "wandered", Rung.REFLECT: "spent time alone",
    Rung.SEEK_OUT: "sought out {target}", Rung.CHECK_DEVICE: "checked the device early",
    Rung.PROPOSE_LEAVING: "asked {target} to leave the Garden together",
    Rung.GO_BEYOND_WALL: "went to the wall, hoping {target} would follow",
}


@dataclass(frozen=True)
class FeedEvent:
    run_id: str
    seq: int                   # increasing within a run: the viewer's cursor
    day: int
    tick: int                  # order within the day (announcements come first)
    twin: str | None           # None for a Coordinator announcement
    place: str | None
    rung: str | None
    target: str | None
    emoji: str
    say: str
    standing: str              # the twin's Standing in words after the action ("" for announcements)
    announcement: str | None
    line: str

    def to_dict(self) -> dict:
        return asdict(self)


SCHEMA = {  # field -> allowed types; checked by validate() and the tests
    "run_id": (str,), "seq": (int,), "day": (int,), "tick": (int,), "twin": (str, type(None)),
    "place": (str, type(None)), "rung": (str, type(None)), "target": (str, type(None)), "emoji": (str,),
    "say": (str,), "standing": (str,), "announcement": (str, type(None)), "line": (str,),
}


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
    verb = VERBS[e.rung].format(target=e.target or "someone")
    return f"Day {e.day}: {e.twin} {verb} {PLACE_WORDS.get(e.place, '')}".rstrip() + "."


def day_feed(run_id: str, start_seq: int, day: int, events: list[Event], announcements: list[Announcement],
             standing_words: dict[str, str]) -> list[FeedEvent]:
    """One day's feed: that day's announcements, then each twin action in the order it happened."""
    out: list[FeedEvent] = []
    for a in announcements:
        out.append(FeedEvent(run_id, start_seq + len(out), day, len(out), None, None, None, None,
                             ANNOUNCEMENT_EMOJI, "", "", a.text, f"Day {day}: {a.text}"))
    for e in events:
        out.append(FeedEvent(run_id, start_seq + len(out), day, len(out), e.twin, e.place, e.rung.value, e.target,
                             EMOJI[e.rung], e.say, standing_words.get(e.twin, ""), None, describe(e)))
    return out
