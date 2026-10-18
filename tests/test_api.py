"""Seam 3 (local): POST /simulations with the fake model ends with a stored result."""
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore


def client():
    return TestClient(create_app(MemoryStore()))


def test_start_simulation_returns_a_done_record_with_a_breakout():
    c = client()
    res = c.post("/simulations", json={"scenario": "breakout"})
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "done"
    assert body["result"]["outcome"] == "breakout"
    assert body["result"]["pair"] == ["Mara", "Ren"]


def test_the_result_can_be_read_back():
    c = client()
    sim_id = c.post("/simulations", json={"scenario": "timeout", "max_days": 3}).json()["id"]
    body = c.get(f"/simulations/{sim_id}").json()
    assert body["result"]["outcome"] == "timeout"
    assert body["result"]["day"] == 3


def test_unknown_simulation_is_404():
    assert client().get("/simulations/nope").status_code == 404


def test_live_limits_refuse_unlisted_models_extra_runs_and_a_second_live_simulation():
    from api.main import LiveLimits
    from fastapi import HTTPException

    limits = LiveLimits({"ilmu:ilmu-mini-v3.3"}, max_sims=1, max_runs=1)
    limits.admit(["fake:a", "fake:b"], 6, "scripted")  # scripted models are never refused
    for models, runs, status in ((["gemini:x"], 1, 403), (["ilmu:ilmu-mini-v3.3"], 2, 400)):
        try:
            limits.admit(models, runs, "x")
            raise AssertionError("should have been refused")
        except HTTPException as e:
            assert e.status_code == status
    limits = LiveLimits(None, max_sims=1)
    limits.admit(["ilmu:ilmu-mini-v3.3"], 1, "first")
    try:
        limits.admit(["ilmu:ilmu-mini-v3.3"], 1, "second")
        raise AssertionError("should have been refused")
    except HTTPException as e:
        assert e.status_code == 429 and "first" in e.detail
    limits.release("first")
    limits.admit(["ilmu:ilmu-mini-v3.3"], 1, "second")
