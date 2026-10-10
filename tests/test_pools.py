"""D2: demo pool loader and answer-key check."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import speed_dating as sd
from garden.pools import check_answer_key, eligible_women, load_pool


def person(iid, gender, **extra):
    row = {f: None for f in sd.PRE_DATE_FIELDS} | {"iid": iid, "gender": gender, "wave": 1, "age": 25.0,
                                                   "field": "Law", "career": "lawyer", "goal": 2.0}
    return row | extra


def fake_dates() -> pd.DataFrame:
    """Woman 1 met men 10-15: matched 10 and 11. Woman 2 matched only 10."""
    rows = []
    for pid, match in [(10, 1), (11, 1), (12, 0), (13, 0), (14, 0), (15, 0)]:
        rows.append(person(1, 0, pid=pid, match=match))
        rows.append(person(pid, 1, pid=1, match=match))
    for pid, match in [(10, 1), (12, 0), (13, 0), (14, 0)]:
        rows.append(person(2, 0, pid=pid, match=match))
    return pd.DataFrame(rows)


def test_eligible_women_need_two_matches_and_three_non_matches():
    assert [w["iid"] for w in eligible_women(fake_dates())] == [1]


def test_a_pool_is_her_twin_her_matches_and_some_non_matches():
    pool = load_pool(fake_dates(), 1, non_matches=3)
    assert pool.woman.iid == 1 and pool.woman.gender == "f"
    assert len(pool.men) == 5 and len(pool.matched) == 2
    matched_iids = {m.iid for m in pool.men if m.alias in pool.matched}
    assert matched_iids == {10, 11}
    assert len({t.alias for t in pool.twins}) == 6  # aliases unique within the pool
    assert set(pool.personas) == {t.alias for t in pool.twins}


def test_a_man_cannot_be_the_woman():
    with pytest.raises(KeyError):
        load_pool(fake_dates(), 10)


def test_answer_key_check():
    perfect = check_answer_key(["A", "B", "x", "y", "z"], frozenset({"A", "B"}))
    assert perfect.matches_on_top and perfect.pairs_in_order == 1.0
    assert perfect.matched_ranks == {"A": 1, "B": 2}
    mixed = check_answer_key(["x", "A", "y", "B", "z"], frozenset({"A", "B"}))
    assert not mixed.matches_on_top and mixed.pairs_in_order == 0.5  # chance level
    worst = check_answer_key(["x", "y", "A", "B"], frozenset({"A", "B"}))
    assert worst.pairs_in_order == 0.0


def test_api_simulates_a_real_pool_and_returns_the_answer_key():
    app = create_app(MemoryStore())
    app.state.dates = fake_dates()
    client = TestClient(app)
    assert [w["iid"] for w in client.get("/pools").json()] == [1]
    body = client.post("/simulations", json={"pool_iid": 1, "max_days": 3, "seeds": [0]}).json()
    assert body["pool_iid"] == 1 and len(body["ranking"]) == 5
    key = body["answer_key"]
    assert len(key["matched"]) == 2 and set(key["matched_ranks"]) == set(key["matched"])
    assert 0.0 <= key["pairs_in_order"] <= 1.0


def test_unknown_pool_is_404():
    app = create_app(MemoryStore())
    app.state.dates = fake_dates()
    assert TestClient(app).post("/simulations", json={"pool_iid": 99}).status_code == 404


def test_ties_count_as_half_so_no_information_scores_chance():
    ranked = ["A", "B", "x", "y"]  # alphabetical, everyone tied
    tied = {n: (0, 0.0) for n in ranked}
    check = check_answer_key(ranked, frozenset({"A", "B"}), tied)
    assert check.pairs_in_order == 0.5 and not check.matches_on_top
