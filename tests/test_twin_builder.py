"""D4: a completed Q&A becomes a twin with an anonymous alias; edits override; it can enter the Garden."""
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import demo
from garden import onboarding as qa
from garden import twin_builder as tb

LONG = "I love slow Sunday mornings with coffee, long walks and calling my sister."


def extraction(rebel=0.8, n=30):
    sections = list(tb.SECTIONS)
    return tb.Extraction(
        memories=[tb.Memory(section=sections[i % 5], text=f"I remember moment {i}.") for i in range(n)],
        attachment_style="secure", values=["honesty", "adventure"], dealbreakers=["dishonesty"],
        rebelliousness=rebel, rebelliousness_evidence=["rules_bend", "not_a_question"])


class Extractor:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def sample_json(self, prompt, schema):
        self.prompts.append(prompt)
        return self.reply


def client(store=None, reply=None, uid="user-1"):
    reply = tb.dumps(extraction()) if reply is None else reply
    model = Extractor(reply)
    app = create_app(store or MemoryStore(), verify_token=lambda token: token, followup_model=lambda: None,
                     extraction_model=lambda: ("fake:extractor", model))
    return TestClient(app, headers={"Authorization": f"Bearer {uid}"}), model


def complete_qa(c):
    c.post("/me/consent", json={"agree": True, "version": qa.CONSENT_VERSION})
    for q in qa.QUESTIONS:
        assert c.post("/me/answers", json={"question_id": q.id, "text": f"{LONG} ({q.id})"}).status_code == 200


def test_a_completed_q_and_a_produces_a_twin_with_an_anonymous_alias():
    c, model = client()
    complete_qa(c)
    twin = c.post("/me/twin").json()
    assert twin["alias"] in tb.ALIASES and twin["memory_count"] == 30
    assert [s["id"] for s in twin["sections"]] == list(tb.SECTIONS)
    assert twin["rebelliousness_because"] == [qa.BY_ID["rules_bend"].text]  # unknown ids dropped
    assert len(model.prompts) == 1 and "[rules_bend]" in model.prompts[0]  # one call, over every answer


def test_the_alias_never_reveals_the_user_and_stays_stable():
    assert tb.alias_for("user-1") == tb.alias_for("user-1")
    assert not set(tb.ALIASES) & set(demo.PERSONAS)


def test_a_twin_needs_consent_and_every_answer():
    c, _ = client()
    assert c.post("/me/twin").status_code == 403
    c.post("/me/consent", json={"agree": True, "version": qa.CONSENT_VERSION})
    assert c.post("/me/twin").status_code == 409


def test_a_reply_that_breaks_the_schema_is_a_clear_error():
    c, _ = client(reply='{"memories": "lots"}')
    complete_qa(c)
    assert c.post("/me/twin").status_code == 502
    assert c.get("/me/twin").status_code == 404


def test_edits_are_stored_as_overriding_memories():
    c, _ = client()
    complete_qa(c)
    c.post("/me/twin")
    twin = c.put("/me/twin/sections/rules", json={"text": "I keep rules unless love asks.\nThen I don't."}).json()
    rules = next(s for s in twin["sections"] if s["id"] == "rules")
    assert rules["edited"] and rules["text"] == "I keep rules unless love asks. Then I don't."
    assert twin["memory_count"] == 30 - 6 + 2  # the extracted rules memories are replaced


def test_clearing_an_edit_goes_back_to_the_extraction():
    c, _ = client()
    complete_qa(c)
    c.post("/me/twin")
    c.put("/me/twin/sections/life", json={"text": "Mine."})
    twin = c.put("/me/twin/sections/life", json={"text": ""}).json()
    assert not next(s for s in twin["sections"] if s["id"] == "life")["edited"]
    assert c.put("/me/twin/sections/nope", json={"text": "x"}).status_code == 404


def test_rebuilding_keeps_the_users_edits():
    store = MemoryStore()
    c, _ = client(store)
    complete_qa(c)
    c.post("/me/twin")
    c.put("/me/twin/sections/past", json={"text": "My words."})
    again, _ = client(store, reply=tb.dumps(extraction(rebel=0.1)))
    twin = again.post("/me/twin").json()
    assert next(s for s in twin["sections"] if s["id"] == "past")["text"] == "My words."
    assert twin["rebelliousness"] == 0.1


@pytest.mark.parametrize("rebel,expected", [(0.0, 0.8), (0.5, 0.6), (1.0, 0.4)])
def test_rebelliousness_sets_the_verdict_threshold(rebel, expected):
    assert tb.threshold(rebel) == expected


def test_her_twin_can_be_the_woman_in_a_simulation():
    store = MemoryStore()
    c, _ = client(store)
    complete_qa(c)
    alias = c.post("/me/twin").json()["alias"]
    c.put("/me/twin/sections/rules", json={"text": "I would cross any wall for love."})
    sim = c.post("/simulations", json={"my_twin": True, "scenario": "breakout", "seeds": [0]}).json()
    assert sim["woman"] == alias and alias in sim["twins"] and "Mara" not in sim["twins"]
    assert sim["result"]["outcome"] == "breakout" and alias in sim["result"]["pair"]
    assert [r["candidate"] for r in sim["ranking"]][0] == demo.MAN


def test_her_persona_and_threshold_reach_the_world():
    her = tb.new_twin("u", extraction(rebel=1.0), "fake", "now")
    pool = demo.with_her_twin(her["alias"], tb.persona_text(her), tb.threshold(1.0))
    assert pool.personas[her["alias"]].startswith("I remember moment")
    assert pool.thresholds == ((her["alias"], 0.4),) and pool.woman == her["alias"]


def test_a_my_twin_simulation_needs_sign_in_and_a_twin():
    c, _ = client()
    anonymous = TestClient(c.app)
    assert anonymous.post("/simulations", json={"my_twin": True}).status_code == 401
    assert c.post("/simulations", json={"my_twin": True}).status_code == 404


def test_without_an_extraction_model_building_is_unavailable():
    app = create_app(MemoryStore(), verify_token=lambda t: t, followup_model=lambda: None,
                     extraction_model=lambda: None)
    c = TestClient(app, headers={"Authorization": "Bearer u"})
    complete_qa(c)
    assert c.post("/me/twin").status_code == 503


def test_a_model_outage_is_a_503_not_a_crash():
    class Down:
        def sample_json(self, prompt, schema):
            raise RuntimeError("429 RESOURCE_EXHAUSTED limit: 0")

    app = create_app(MemoryStore(), verify_token=lambda t: t, followup_model=lambda: None,
                     extraction_model=lambda: ("gemini:pro", Down()))
    c = TestClient(app, headers={"Authorization": "Bearer u"})
    complete_qa(c)
    res = c.post("/me/twin")
    assert res.status_code == 503 and "limit" not in res.json()["detail"]
