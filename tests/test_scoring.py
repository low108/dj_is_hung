"""C2 seam 2: the scorer, from run results."""
from garden.batch import PriceLevel, RunRecord, RunSpec
from garden.engine import RunResult
from garden.engine_types import OutcomeKind
from garden.scoring import score, wilson

MEN = ["Ren", "Jun", "Kai"]
LOW, HIGH = PriceLevel.LOW, PriceLevel.HIGH


def rec(i, price, pair=None, outcome=None):
    outcome = outcome or (OutcomeKind.BREAKOUT if pair else OutcomeKind.TIMEOUT)
    return RunRecord(RunSpec(f"r{i}", "fake:a", price, i), RunResult(outcome, 5, pair), 1.0)


def by_name(scores):
    return {s.candidate: s for s in scores}


def test_no_breakouts_ranks_everyone_as_never():
    scores = score([rec(0, LOW), rec(1, HIGH)], "Mara", MEN)
    assert all(s.price is None and s.breakouts == 0 for s in scores)
    assert [s.candidate for s in scores] == sorted(MEN)  # ties broken by name


def test_breakouts_only_at_the_lowest_level():
    records = [rec(0, LOW, ("Mara", "Jun")), rec(1, LOW), rec(2, HIGH), rec(3, HIGH)]
    s = by_name(score(records, "Mara", MEN))
    assert s["Jun"].price is LOW and (s["Jun"].breakouts, s["Jun"].runs) == (1, 2)
    assert s["Ren"].price is None


def test_breakouts_at_every_level_score_the_highest_and_rank_first():
    records = [rec(0, LOW, ("Mara", "Ren")), rec(1, HIGH, ("Mara", "Ren")), rec(2, HIGH),
               rec(3, LOW, ("Jun", "Mara")), rec(4, LOW, ("Jun", "Mara"))]
    scores = score(records, "Mara", MEN)
    assert scores[0].candidate == "Ren" and scores[0].price is HIGH  # high beats a better low-price rate
    assert scores[1].candidate == "Jun" and scores[1].price is LOW
    assert scores[0].breakouts_by_price == {"low": (1, 3), "high": (1, 2)}


def test_a_single_run():
    scores = by_name(score([rec(0, HIGH, ("Mara", "Kai"))], "Mara", MEN))
    k = scores["Kai"]
    assert (k.price, k.breakouts, k.runs) == (HIGH, 1, 1)
    assert 0 < k.ci_low < 1 and k.ci_high == 1.0  # one run: very wide range


def test_excluded_runs_are_never_scored():
    records = [rec(0, HIGH, ("Mara", "Ren"), OutcomeKind.EXCLUDED), rec(1, HIGH)]
    s = by_name(score(records, "Mara", MEN))
    assert s["Ren"].price is None and s["Ren"].runs == 1


def test_breakouts_without_her_do_not_count_for_him():
    s = by_name(score([rec(0, HIGH, ("Jun", "Ren"))], "Mara", MEN))
    assert s["Ren"].price is None


def test_wilson_interval():
    assert wilson(0, 0) == (0.0, 1.0)
    low, high = wilson(7, 10)
    assert 0.39 < low < 0.40 and 0.89 < high < 0.90


def test_the_api_returns_a_ranking_with_price_and_confidence_range():
    from fastapi.testclient import TestClient

    from api.main import create_app
    from api.store import MemoryStore

    body = TestClient(create_app(MemoryStore())).post("/simulations", json={"max_days": 5}).json()
    top = body["ranking"][0]
    assert top["candidate"] == "Ren" and top["price"] == "high"  # the scripted breakout is Mara + Ren
    assert 0 <= top["ci_low"] <= top["ci_high"] <= 1
    assert len(body["ranking"]) == 5
