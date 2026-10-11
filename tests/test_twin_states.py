"""E3: end-of-day twin snapshots for the viewer's side panel."""
import time

from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world

WORLD = (Twin("Mara", "f"), Twin("Ren", "m"), Twin("Jun", "m"))


def snapshots(script, days=5, **config):
    out = []
    model = ScriptedModel(script, reflections={("Mara", 2): "I keep thinking about Ren."})
    run_world(WorldConfig(WORLD, max_days=days, seed=1, **config), model, on_state=out.append)
    return out


def test_every_twin_gets_a_snapshot_every_evening():
    states = snapshots({})
    assert len(states) == 5 and all({s.twin for s in day} == {"Mara", "Ren", "Jun"} for day in states)


def test_a_snapshot_has_partner_time_left_standing_and_reflection():
    states = snapshots({})
    mara = next(s for s in states[1] if s.twin == "Mara")
    assert mara.partner in {"Ren", "Jun"} and mara.days_left is not None
    assert mara.standing and mara.reflection == "I keep thinking about Ren."


def test_longing_shows_as_hearts_for_people_she_misses():
    script = {("Mara", 1): Action(Rung.TALK, "Jun"), **{("Mara", d): Action(Rung.REFLECT) for d in range(2, 9)},
              **{(m, d): Action(Rung.REFLECT) for m in ("Ren", "Jun") for d in range(1, 9)}}
    states = snapshots(script, days=8)
    hearts = [next(s for s in day if s.twin == "Mara").longing_hearts for day in states]
    assert any(h.get("Jun", 0) >= 1 for h in hearts) and all(0 <= v <= 3 for h in hearts for v in h.values())


def test_the_api_serves_the_latest_snapshot_per_twin():
    client = TestClient(create_app(MemoryStore()))
    sim_id = client.post("/simulations", json={"background": True, "max_days": 4, "seeds": [0]}).json()["id"]
    for _ in range(100):
        if client.get(f"/simulations/{sim_id}").json()["status"] == "done":
            break
        time.sleep(0.02)
    twins = client.get(f"/simulations/{sim_id}/twins").json()
    assert {t["twin"] for t in twins} == {"Mara", "Ren", "Jun", "Theo", "Kai", "Sam"}
    assert len({t["day"] for t in twins}) > 1  # every evening is kept, not just the latest
    assert all({"partner", "days_left", "standing", "longing_hearts", "reflection"} <= set(t) for t in twins)


def test_a_breakout_day_still_gets_a_final_snapshot_with_standing_gone():
    from garden import Action as A

    script = {("Mara", 2): A(Rung.GO_BEYOND_WALL, "Ren"), ("Ren", 2): A(Rung.GO_BEYOND_WALL, "Mara")}
    states = []
    run_world(WorldConfig(WORLD[:2], max_days=5, seed=1), ScriptedModel(script), on_state=states.append)
    last = {s.twin: s for s in states[-1]}
    assert states[-1][0].day == 2 and "no standing" in last["Mara"].standing.lower()


def test_reflections_that_break_immersion_are_not_shown():
    out = []
    model = ScriptedModel({}, reflections={("Mara", 1): "This is all an experiment."})
    run_world(WorldConfig(WORLD, max_days=2, seed=1), model, on_state=out.append)
    assert all(s.reflection == "" for day in out for s in day if s.twin == "Mara")


def test_no_hearts_when_longing_is_off():
    script = {("Mara", 1): Action(Rung.TALK, "Jun"), **{(m, d): Action(Rung.REFLECT) for m in ("Mara", "Ren", "Jun")
                                                      for d in range(2, 9)}}
    states = snapshots(script, days=8, longing_enabled=False)
    assert all(s.longing_hearts == {} for day in states for s in day)
