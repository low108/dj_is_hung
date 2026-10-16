"""About you: profile facts, the Mini-IPIP and 100 partner points become facts the twin knows, worded by
fixed templates; a user's twin is told never to invent facts about the real person behind it."""
import pytest
from pydantic import ValidationError

from garden import about_me as am
from garden import onboarding as qa
from garden import twin_builder as tb
from tests.test_twin_builder import LONG, client, complete_qa, extraction

PROFILE = {"age": 29, "work": "Nurse", "city": "Singapore", "loves": ["hiking", "cooking"], "dislikes": ["clubbing"]}
POINTS = {"attractive": 10, "sincere": 40, "intelligent": 25, "fun": 15, "ambitious": 5, "shared_interests": 5}


def answers(**trait_level):
    """All 20 Mini-IPIP answers placing each trait at a level (1-5); reverse-keyed items flipped."""
    return {i: (6 - trait_level.get(t, 3) if rev else trait_level.get(t, 3)) for i, _, t, rev in am.MINI_IPIP}


def test_the_mini_ipip_scores_each_trait_from_its_four_items():
    scores = am.trait_scores(am.Personality(answers=answers(E=5, N=1)))
    assert scores == {"E": 5.0, "A": 3.0, "C": 3.0, "N": 1.0, "I": 3.0}
    assert len(am.MINI_IPIP) == 20 and all(sum(1 for i in am.MINI_IPIP if i[2] == t) == 4 for t in am.TRAITS)


def test_the_forms_become_first_person_facts():
    facts = [m["text"] for m in am.memories({"profile": PROFILE, "personality": {"answers": answers(E=5, N=1)},
                                              "preferences": {"points": POINTS}})]
    assert facts[:5] == ["I am 29 years old.", "My work: Nurse.", "I live in Singapore.", "I love hiking and cooking.",
                         "I don't care much for clubbing."]
    assert am.SAYS["E"][0] in facts and am.SAYS["N"][1] in facts and am.SAYS["A"][0] not in facts  # middling: silent
    assert "In a partner, what matters most to me is that they are sincere, then intelligent." in facts
    assert "Whether a partner is ambitious matters less to me." in facts


@pytest.mark.parametrize("bad", [
    {"profile": PROFILE | {"age": 15}},
    {"profile": PROFILE | {"loves": ["hiking"], "dislikes": ["hiking"]}},
    {"profile": PROFILE | {"loves": ["skydiving"]}},
    {"personality": {"answers": {"e1": 3}}},
    {"preferences": {"points": POINTS | {"fun": 16}}},
])
def test_bad_forms_are_refused(bad):
    with pytest.raises(ValidationError):
        am.memories(bad)


def test_the_about_forms_need_consent_save_and_reach_the_twin():
    c, _ = client()
    assert c.put("/me/about/profile", json=PROFILE).status_code == 403  # consent first
    complete_qa(c)
    assert c.put("/me/about/profile", json=PROFILE).status_code == 200
    assert c.put("/me/about/preferences", json={"points": POINTS | {"fun": 99}}).status_code == 422
    saved = c.put("/me/about/preferences", json={"points": POINTS}).json()
    assert saved["status"] == {"profile": True, "personality": False, "preferences": True}
    assert c.get("/me/onboarding").json()["about"]["profile"] is True
    twin = c.post("/me/twin").json()
    assert twin["about"][0]["text"] == "I am 29 years old."
    assert c.put("/me/about/nonsense", json={}).status_code == 404


def test_a_users_twin_knows_its_form_facts_first_and_must_not_invent():
    twin = tb.new_twin("u", extraction(), "fake", "now", about={"profile": PROFILE})
    _, persona = tb.garden_inputs(twin)
    lines = persona.splitlines()
    assert lines[0] == "I am 29 years old." and lines[-1] == am.STRICT_GROUNDING
