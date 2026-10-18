"""Couples pools: twins built from both partners' Big Five facets (Weidmann, Purol et al. 2023)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import couples as c


def table(n=12, overrides=None):
    """A synthetic file shaped like datasimilarity.csv: everyone at their gender's mean unless overridden."""
    rows = []
    for i in range(n):
        row = {"RelationshipSatisfaction_P1": 4.0, "RelationshipSatisfaction_P2": 4.0}
        for f, (m_mean, _, f_mean, _) in c.TABLE1.items():
            pooled = (m_mean + f_mean) / 2
            row[f"{f}C_P1"], row[f"{f}C_P2"] = f_mean - pooled, m_mean - pooled  # centred, as in the file
        rows.append(row)
    data = pd.DataFrame(rows)
    for (i, col), value in (overrides or {}).items():
        data.loc[i, col] = value
    return data


def test_centred_scores_are_restored_to_the_1_to_5_scale():
    data = table()
    assert c.scores(data, 0, 1)["Anxiety"] == pytest.approx(2.83)  # the female mean
    assert c.scores(data, 0, 2)["Assertiveness"] == pytest.approx(3.54)  # the male mean


def test_a_persona_is_the_most_distinctive_facets_in_their_own_words():
    pooled = (2.41 + 2.83) / 2
    data = table(overrides={(0, "AnxietyC_P1"): 4.9 - pooled, (0, "SociabilityC_P1"): 1.2 - ((3.15 + 3.25) / 2)})
    said = c.person(data, 0, 1, "Ada").memories
    # sociability is 1.99 SDs below her gender's mean, anxiety 1.95 above: the further one comes first
    assert said == (c.SAYS["Sociability"][1], c.SAYS["Anxiety"][0])
    # everything else is at her gender's mean: nothing more distinctive to say


def test_traits_are_judged_against_the_twins_own_gender():
    # 3.54 assertiveness is average for a man but well above average for a woman.
    pooled = (3.54 + 2.99) / 2
    data = table(overrides={(0, "AssertivenessC_P1"): 3.54 - pooled, (0, "AssertivenessC_P2"): 3.54 - pooled})
    assert c.SAYS["Assertiveness"][0] in c.person(data, 0, 1, "Ada").memories
    assert c.SAYS["Assertiveness"][0] not in c.person(data, 0, 2, "Abe").memories


def test_a_pool_is_her_her_real_partner_and_six_men_from_other_couples():
    pool = c.load_pool(table(), 3)
    assert pool.woman.couple == 3 and len(pool.men) == 7
    partner = next(m for m in pool.men if m.alias == pool.partner)
    assert partner.couple == 3 and {m.couple for m in pool.men if m is not partner}.isdisjoint({3})
    assert [m.alias for m in pool.men] == sorted(m.alias for m in pool.men)  # order doesn't give him away
    assert pool == c.load_pool(table(), 3)  # the same couple always gets the same men


def test_couples_missing_data_are_refused():
    with pytest.raises(KeyError):
        c.load_pool(table(overrides={(2, "TrustC_P2"): float("nan")}), 2)


def test_a_simulation_can_run_on_a_couple_with_her_partner_as_the_answer_key(monkeypatch):
    monkeypatch.setattr(c, "load", lambda path=c.DEFAULT_PATH: table())
    sim = TestClient(create_app(MemoryStore())).post("/simulations", json={"couple_id": 5, "seeds": [0],
                                                                        "scenario": "timeout"}).json()
    assert sim["status"] == "done" and sim["couple"]["partner"] in sim["twins"]
    assert sim["answer_key"]["matched"] == [sim["couple"]["partner"]]
    assert sim["couple"]["satisfaction"] == {"her": 4.0, "him": 4.0}


@pytest.mark.skipif(not c.DEFAULT_PATH.exists(), reason="couples data not downloaded")
def test_the_real_file_has_p1_as_the_female_partner():
    data = c.load()
    assert data.RelationshipSatisfaction_P1.mean() == pytest.approx(4.42, abs=0.01)  # paper: female 4.42
    assert data.RelationshipSatisfaction_P2.mean() == pytest.approx(4.47, abs=0.01)  # paper: male 4.47
    restored = {f: data[f"{f}C_P1"].mean() + (m + fm) / 2 for f, (m, _, fm, _) in c.TABLE1.items()}
    assert all(restored[f] == pytest.approx(c.TABLE1[f][2], abs=0.02) for f in c.TABLE1)  # female means
