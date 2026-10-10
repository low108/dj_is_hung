"""C1: price levels and parallel runs."""
import time

from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import Action, Rung, ScriptedModel
from garden.batch import PriceLevel, plan, run_simulation
from garden.demo import FAKE_MODELS, POOL

PRICES = list(PriceLevel)


def test_a_simulation_is_models_x_prices_x_seeds_with_unique_ids():
    specs = plan(FAKE_MODELS, PRICES, [0, 1])
    assert len(specs) == 12
    assert len({s.run_id for s in specs}) == 12
    assert {(s.model, s.price, s.seed) for s in specs} == {(m, p, s) for m in FAKE_MODELS for p in PRICES for s in (0, 1)}


class Slow(ScriptedModel):
    def choose_action(self, *args, **kw):
        time.sleep(0.05)
        return super().choose_action(*args, **kw)


def test_runs_execute_in_parallel_and_wall_time_is_recorded():
    specs = plan(FAKE_MODELS, PRICES, [0, 1])
    sim = run_simulation(specs, POOL, lambda spec: Slow(), max_days=2)
    serial = sum(r.wall_seconds for r in sim.records)
    assert len(sim.records) == 12 and all(r.result for r in sim.records)
    assert sim.wall_seconds < serial / 3  # 12 runs on 12 threads, not one after another


def test_each_run_records_its_price_level_and_seed_and_the_price_sets_standing():
    specs = plan(["fake:a"], PRICES, [3])
    sim = run_simulation(specs, POOL, lambda spec: ScriptedModel(), max_days=1)
    for record in sim.records:
        first = next(e for e in record.result.events if e.day == 1)
        assert first.standing_before == record.spec.price.standing
        assert record.spec.seed == 3


def test_one_failed_run_does_not_sink_the_simulation():
    class Boom(ScriptedModel):
        def choose_action(self, *a, **k):
            raise RuntimeError("model down")

    specs = plan(["fake:a", "fake:b"], [PriceLevel.LOW], [0])
    sim = run_simulation(specs, POOL, lambda spec: Boom() if spec.model == "fake:b" else ScriptedModel(), max_days=1)
    assert [r.error is None for r in sim.records] == [True, False]
    assert "model down" in sim.records[1].error
    assert len(sim.scorable) == 1


def test_one_start_simulation_produces_12_run_results():
    body = TestClient(create_app(MemoryStore())).post("/simulations", json={"max_days": 4}).json()
    assert body["status"] == "done" and body["runs_planned"] == 12
    assert len(body["runs"]) == 12 and body["wall_seconds"] >= 0
    assert {(r["price"], r["seed"]) for r in body["runs"]} == {("low", 0), ("low", 1), ("high", 0), ("high", 1)}
    assert all(r["result"]["outcome"] == "breakout" for r in body["runs"])  # the scripted breakout scenario


def test_parallel_runs_share_one_rate_limiter_per_model():
    from garden.llm import shared_pacer

    a = shared_pacer(("ilmu", "test-model"), 5)
    b = shared_pacer(("ilmu", "test-model"), 5)
    assert a is b
    assert shared_pacer(("ilmu", "test-model"), None) is None
