"""E1: the event contract and the live event stream."""
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.feed import SCHEMA, day_feed, validate


def collect(script, days=4):
    captured = []
    run_world(WorldConfig((Twin("Mara", "f"), Twin("Ren", "m"), Twin("Jun", "m")), max_days=days, seed=1),
              ScriptedModel(script), lambda *args: captured.append(args))
    seq, out = 0, []
    for day, events, announcements, words in captured:
        items = day_feed("r00", seq, day, events, announcements, words)
        seq += len(items)
        out += [i.to_dict() for i in items]
    return out


def test_every_feed_event_matches_the_contract():
    feed = collect({("Mara", 2): Action(Rung.SEEK_OUT, "Ren", "I kept thinking about you.")})
    assert feed
    for event in feed:
        validate(event)
    assert [e["seq"] for e in feed] == list(range(len(feed)))  # a gapless cursor


def test_feed_lines_read_like_sentences():
    feed = collect({("Mara", 2): Action(Rung.SEEK_OUT, "Ren")})
    line = next(e["line"] for e in feed if e["twin"] == "Mara" and e["day"] == 2)
    assert line.startswith("Day 2: Mara sought out Ren ") and line.endswith(".")
    assert any(e["announcement"] and "paired for" in e["announcement"] for e in feed)


def test_validate_rejects_a_broken_event():
    good = collect({})[0]
    with pytest.raises(ValueError):
        validate({k: v for k, v in good.items() if k != "line"})
    with pytest.raises(ValueError):
        validate(good | {"place": "the moon"})
    assert set(good) == set(SCHEMA)


def test_a_background_simulation_streams_the_featured_run_then_finishes():
    client = TestClient(create_app(MemoryStore()))
    started = client.post("/simulations", json={"background": True, "max_days": 6, "scenario": "breakout"}).json()
    assert started["status"] == "running" and started["featured_run"] == "r00"
    sim_id = started["id"]
    for _ in range(100):
        if client.get(f"/simulations/{sim_id}").json()["status"] == "done":
            break
        time.sleep(0.05)
    events = client.get(f"/simulations/{sim_id}/events").json()
    assert events and all(e["run_id"] == "r00" for e in events)
    later = client.get(f"/simulations/{sim_id}/events", params={"after": events[-3]["seq"]}).json()
    assert [e["seq"] for e in later] == [e["seq"] for e in events[-2:]]
    assert any("went to the wall" in e["line"] for e in events)  # the scripted breakout
