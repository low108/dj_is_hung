"""E4: every finished run is saved and can be replayed without running anything again."""
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import replay
from garden.feed import validate


def app(tmp_path, store=None):
    return TestClient(create_app(store or MemoryStore(), replay_dir=tmp_path))


def simulate(client, **body):
    return client.post("/simulations", json={"max_days": 6, **body}).json()


def test_every_finished_run_is_saved_for_replay(tmp_path):
    sim = simulate(app(tmp_path), seeds=[0, 1])
    saved = replay.list_replays(tmp_path)
    assert sorted(r["run_id"] for r in saved) == sorted(r["run_id"] for r in sim["runs"])
    assert sum(r["featured"] for r in saved) == 1


def test_a_replay_holds_the_runs_feed_and_evenings(tmp_path):
    client = app(tmp_path)
    sim = simulate(client, seeds=[0])
    run = next(r for r in sim["runs"] if r["run_id"] != sim["featured_run"])  # not only the featured run
    body = client.get(f"/replays/{sim['id']}/{run['run_id']}").json()
    assert body["outcome"] == run["result"]["outcome"] and body["twins"] == sim["twins"]
    assert body["events"] and body["twin_states"]
    for event in body["events"]:
        validate(event)
    assert [e["seq"] for e in body["events"]] == list(range(len(body["events"])))


def test_the_featured_replay_matches_what_was_streamed_live(tmp_path):
    client = app(tmp_path)
    sim = simulate(client)
    live = client.get(f"/simulations/{sim['id']}/events").json()
    stored = client.get(f"/replays/{sim['id']}/{sim['featured_run']}").json()
    assert stored["events"] == live
    assert stored["twin_states"] == client.get(f"/simulations/{sim['id']}/twins").json()


def test_replaying_makes_no_model_calls(tmp_path, monkeypatch):
    import garden.demo as demo

    sim = simulate(app(tmp_path))

    def no_models(*a, **k):
        raise AssertionError("replay must not build a model")

    monkeypatch.setattr(demo, "make_twin_model", no_models)
    fresh = app(tmp_path)  # a restarted server: nothing in memory, only the files
    last = fresh.get("/replays").json()[0]
    assert last["sim_id"] == sim["id"]
    assert fresh.get(f"/replays/{last['sim_id']}/{last['run_id']}").json()["events"]


def test_the_picker_lists_the_newest_simulation_first_with_its_identity(tmp_path):
    client = app(tmp_path)
    simulate(client, scenario="timeout")
    newest = simulate(client, scenario="breakout")
    rows = client.get("/replays").json()
    n = len(newest["runs"])
    assert [r["run_id"] for r in rows[:n]] == [r["run_id"] for r in newest["runs"]]  # plan order
    assert {r["sim_id"] for r in rows[:n]} == {newest["id"]}
    first = rows[0]
    assert set(first) == set(replay.SUMMARY_FIELDS)
    assert first["scenario"] == "breakout" and first["model"].startswith("fake:")


def test_unknown_or_unsafe_replays_are_404(tmp_path):
    client = app(tmp_path)
    assert client.get("/replays/nope/r00").status_code == 404
    assert client.get("/replays/..%2F..%2Fetc/passwd").status_code == 404


def test_without_a_replay_dir_nothing_is_saved_or_listed(tmp_path):
    client = TestClient(create_app(MemoryStore()))
    simulate(client)
    assert client.get("/replays").json() == []
    assert not list(tmp_path.iterdir())
