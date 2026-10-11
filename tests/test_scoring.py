"""C2 seam 2: the scorer, from run results."""
from garden.batch import RunRecord, RunSpec
from garden.engine import RunResult
from garden.engine_types import OutcomeKind
from garden.scoring import score, wilson

MEN = ["Ren", "Jun", "Kai"]
EVERYONE_DATED = [("Mara", m) for m in MEN]


def rec(i, pair=None, outcome=None, dated=EVERYONE_DATED):
    outcome = outcome or (OutcomeKind.BREAKOUT if pair else OutcomeKind.TIMEOUT)
    dated = [tuple(sorted(p)) for p in dated]
    return RunRecord(RunSpec(f"r{i}", "fake:a", i), RunResult(outcome, 5, pair, dated=dated), 1.0)


def by_name(scores):
    return {s.candidate: s for s in scores}


def test_no_breakouts_ranks_everyone_level():
    scores = score([rec(0), rec(1)], "Mara", MEN)
    assert all(s.breakouts == 0 and s.runs == 2 for s in scores)
    assert [s.candidate for s in scores] == sorted(MEN)  # ties broken by name


def test_only_runs_where_he_had_a_date_with_her_count_for_him():
    # Kai never got a date in run 1: that run says nothing about him.
    records = [rec(0, ("Mara", "Kai")), rec(1, ("Mara", "Ren"), dated=[("Mara", "Jun"), ("Mara", "Ren")])]
    s = by_name(score(records, "Mara", MEN))
    assert (s["Kai"].breakouts, s["Kai"].runs) == (1, 1)
    assert (s["Ren"].breakouts, s["Ren"].runs) == (1, 2)
    assert (s["Jun"].breakouts, s["Jun"].runs) == (0, 2)


def test_a_breakout_counts_as_a_chance_even_without_a_date():
    s = by_name(score([rec(0, ("Mara", "Kai"), dated=[])], "Mara", MEN))
    assert (s["Kai"].breakouts, s["Kai"].runs) == (1, 1) and s["Ren"].runs == 0


def test_a_single_run():
    k = by_name(score([rec(0, ("Mara", "Kai"))], "Mara", MEN))["Kai"]
    assert (k.breakouts, k.runs) == (1, 1)
    assert 0 < k.ci_low < 1 and k.ci_high == 1.0  # one run: very wide range


def test_excluded_runs_are_never_scored():
    records = [rec(0, ("Mara", "Ren"), OutcomeKind.EXCLUDED), rec(1)]
    s = by_name(score(records, "Mara", MEN))
    assert s["Ren"].breakouts == 0 and s["Ren"].runs == 1


def test_breakouts_without_her_do_not_count_for_him():
    s = by_name(score([rec(0, ("Jun", "Ren"), dated=[("Jun", "Ren"), ("Mara", "Ren")])], "Mara", MEN))
    assert s["Ren"].breakouts == 0


def test_wilson_interval():
    assert wilson(0, 0) == (0.0, 1.0)
    low, high = wilson(7, 10)
    assert 0.39 < low < 0.40 and 0.89 < high < 0.90


def test_the_api_returns_a_ranking_with_a_confidence_range():
    from fastapi.testclient import TestClient

    from api.main import create_app
    from api.store import MemoryStore

    body = TestClient(create_app(MemoryStore())).post("/simulations", json={"max_days": 40}).json()
    top = body["ranking"][0]
    assert top["candidate"] == "Ren" and top["breakouts"] > 0  # the scripted breakout is Mara + Ren
    assert "price" not in top and 0 <= top["ci_low"] <= top["ci_high"] <= 1
    assert len(body["ranking"]) == 5


def test_a_steady_record_outranks_a_lucky_one():
    records = [rec(0, ("Mara", "Kai"), dated=[("Mara", "Kai")])]
    records += [rec(i, ("Mara", "Ren"), dated=[("Mara", "Ren")]) for i in range(1, 10)] + [rec(10)]
    # Kai 1/2 vs Ren 9/10: Ren first, even though a lone breakout is a higher share of fewer runs.
    assert score(records, "Mara", MEN)[0].candidate == "Ren"
