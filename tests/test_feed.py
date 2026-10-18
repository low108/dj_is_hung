"""E1: the event contract and the live event stream."""
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.batch import featured_spec, plan
from garden.feed import SCHEMA, FeedCursor, validate

WORLD = (Twin("Mara", "f"), Twin("Ren", "m"), Twin("Jun", "m"))


def collect(script, days=4, world=WORLD, **config):
    cursor, out = FeedCursor("r00"), []
    run_world(WorldConfig(world, max_days=days, seed=1, **config), ScriptedModel(script),
              lambda item, word: out.append(cursor(item, word).to_dict()))
    return out


def test_every_feed_event_matches_the_contract():
    feed = collect({("Mara", 2): Action(Rung.SEEK_OUT, "Ren", "I kept thinking about you.")})
    assert feed
    for event in feed:
        validate(event)
    assert [e["seq"] for e in feed] == list(range(len(feed)))  # a gapless cursor


def test_feed_lines_read_like_sentences():
    feed = collect({("Mara", 2): Action(Rung.TALK, "Ren", "Hi.")}, world=WORLD[:2])
    line = next(e["line"] for e in feed if e["twin"] == "Mara" and e["day"] == 2)
    assert line.startswith("Day 2: Mara talked with Ren ") and line.endswith(".")
    assert any(e["announcement_kind"] == "paired" for e in feed)


def test_an_announcement_caused_by_an_action_comes_after_it():
    feed = collect({("Mara", 2, 2): Action(Rung.CHECK_DEVICE)})  # after the date's opening exchange
    check = next(i for i, e in enumerate(feed) if e["rung"] == "check_device")
    changed = next(i for i, e in enumerate(feed) if e["announcement_kind"] == "changed")
    assert changed > check


def test_speech_that_slips_out_of_character_is_never_streamed():
    feed = collect({("Jun", 2): Action(Rung.TALK, "Mara", "As an AI, I can't answer that.")})
    jun = next(e for e in feed if e["twin"] == "Jun" and e["day"] == 2)
    assert jun["say"] == "" and jun["rung"] == "reflect"  # he kept to himself that turn instead


def test_no_standing_words_when_standing_is_off():
    feed = collect({}, standing_enabled=False)
    assert all(e["standing"] == "" for e in feed)


def test_validate_rejects_a_broken_event():
    good = collect({})[0]
    with pytest.raises(ValueError):
        validate({k: v for k, v in good.items() if k != "line"})
    with pytest.raises(ValueError):
        validate(good | {"place": "the moon"})
    assert set(good) == set(SCHEMA)


def test_the_featured_run_is_the_first_run():
    specs = plan(["fake:a", "fake:b"], [0, 1])
    assert featured_spec(specs) == specs[0] and featured_spec([]) is None


class Slow(ScriptedModel):
    def choose_action(self, *a, **k):
        time.sleep(0.02)
        return super().choose_action(*a, **k)


def test_events_appear_while_the_simulation_is_still_running(monkeypatch):
    import garden.demo as demo

    monkeypatch.setattr(demo, "make_twin_model", lambda spec, *args, **kw: Slow())
    client = TestClient(create_app(MemoryStore()))
    started = client.post("/simulations", json={"background": True, "max_days": 10, "seeds": [0]}).json()
    sim_id, seen_while_running, status, events = started["id"], False, "running", []
    for _ in range(300):
        status = client.get(f"/simulations/{sim_id}").json()["status"]
        events = client.get(f"/simulations/{sim_id}/events").json()
        if status == "running" and events:
            seen_while_running = True
        if status == "done":
            break
        time.sleep(0.02)
    assert seen_while_running and status == "done"
    later = client.get(f"/simulations/{sim_id}/events", params={"after": events[-3]["seq"]}).json()
    assert [e["seq"] for e in later] == [e["seq"] for e in events[-2:]]
