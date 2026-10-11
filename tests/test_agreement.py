"""F4: runs from every model in the ensemble, each tagged with its model, and per-candidate agreement."""
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import demo, llm
from garden.fake_model import scenario

BY_MODEL = {"fake:a": "breakout", "fake:b": "timeout", "fake:c": "breakout"}


def run(monkeypatch, by_model=BY_MODEL):
    def per_model(spec, personas, fake_scenario="breakout", woman=demo.WOMAN):
        if by_model[spec.model] == "error":
            raise RuntimeError("quota")
        return scenario(by_model[spec.model], woman, demo.MAN)

    monkeypatch.setattr(demo, "make_twin_model", per_model)
    return TestClient(create_app(MemoryStore())).post(
        "/simulations", json={"models": list(by_model), "seeds": [0, 1], "max_days": 6}).json()


def test_every_model_in_the_ensemble_runs_and_each_run_records_its_model(monkeypatch):
    sim = run(monkeypatch)
    assert sim["models"] == sorted(BY_MODEL)
    assert {r["model"] for r in sim["runs"]} == set(BY_MODEL)
    assert all(r["model"] in BY_MODEL for r in sim["runs"])


def test_agreement_counts_the_models_that_reach_the_ensembles_verdict(monkeypatch):
    sim = run(monkeypatch)
    ren = next(a for a in sim["agreement"] if a["candidate"] == demo.MAN)
    assert ren["verdict"] == "high"
    assert ren["by_model"] == {"fake:a": "high", "fake:b": None, "fake:c": "high"}
    assert (ren["agree"], ren["models"]) == (2, 3)
    jun = next(a for a in sim["agreement"] if a["candidate"] == "Jun")
    assert jun["verdict"] is None and (jun["agree"], jun["models"]) == (3, 3)  # all agree: never


def test_agreement_follows_the_ranking_order(monkeypatch):
    sim = run(monkeypatch)
    assert [a["candidate"] for a in sim["agreement"]] == [r["candidate"] for r in sim["ranking"]]


def test_a_model_with_no_scored_runs_is_left_out(monkeypatch):
    sim = run(monkeypatch, {"fake:a": "breakout", "fake:b": "error", "fake:c": "breakout"})
    ren = next(a for a in sim["agreement"] if a["candidate"] == demo.MAN)
    assert set(ren["by_model"]) == {"fake:a", "fake:c"} and (ren["agree"], ren["models"]) == (2, 2)
    assert sim["models"] == sorted(BY_MODEL)  # the failed model still ran, and its runs say why
    assert all(r["error"] for r in sim["runs"] if r["model"] == "fake:b")


def test_the_real_ensemble_is_a_pro_a_flash_and_a_gemma_model():
    assert demo.ENSEMBLE == [f"gemini:{llm.PRO}", f"gemini:{llm.FLASH}", f"gemma:{llm.GEMMA}"]


def test_ensemble_expands_to_the_three_real_models(monkeypatch):
    seen = set()

    def record(spec, *args, **kw):
        seen.add(spec.model)
        return scenario("timeout", demo.WOMAN, demo.MAN)

    monkeypatch.setattr(demo, "make_twin_model", record)
    sim = TestClient(create_app(MemoryStore())).post("/simulations", json={"models": ["ensemble"], "seeds": [0],
                                                                        "max_days": 2}).json()
    assert seen == set(demo.ENSEMBLE) and sim["models"] == sorted(demo.ENSEMBLE)
