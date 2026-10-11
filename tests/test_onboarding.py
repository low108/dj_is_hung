"""D3: Q&A onboarding — consent first, one question at a time, resumable, one follow-up for short answers."""
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import MemoryStore
from garden import onboarding as qa

LONG = "I love slow Sunday mornings with coffee, long walks and calling my sister."


class Asker:
    def __init__(self, reply="What made that week feel so good?"):
        self.reply, self.calls = reply, 0

    def sample_text(self, prompt, **kw):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def client(store=None, model=None):
    # In tests the bearer token *is* the user id.
    app = create_app(store or MemoryStore(), verify_token=lambda token: token, followup_model=lambda: model)
    return TestClient(app, headers={"Authorization": "Bearer user-1"})


def consent(c):
    return c.post("/me/consent", json={"agree": True, "version": qa.CONSENT_VERSION}).json()


def answer(c, text=LONG, qid=None):
    qid = qid or c.get("/me/onboarding").json()["current"]["id"]
    return c.post("/me/answers", json={"question_id": qid, "text": text})


def test_signing_in_is_required():
    anonymous = TestClient(create_app(MemoryStore(), verify_token=lambda t: t, followup_model=lambda: None))
    assert anonymous.get("/me/onboarding").status_code == 401

    def reject(token):
        raise ValueError("bad token")

    assert TestClient(create_app(MemoryStore(), verify_token=reject, followup_model=lambda: None)).get(
        "/me/onboarding", headers={"Authorization": "Bearer x"}).status_code == 401


def test_answers_are_refused_until_consent_is_recorded():
    c = client()
    assert answer(c).status_code == 403
    state = consent(c)
    assert state["consent"]["version"] == qa.CONSENT_VERSION and state["consent"]["text"] == qa.CONSENT_TEXT
    assert answer(c).status_code == 200


def test_consent_must_be_given_to_the_current_text():
    c = client()
    assert c.post("/me/consent", json={"agree": False, "version": qa.CONSENT_VERSION}).status_code == 400
    assert c.post("/me/consent", json={"agree": True, "version": "old"}).status_code == 409


def test_a_user_can_complete_every_question_one_at_a_time():
    c = client()
    consent(c)
    seen = []
    while not (state := c.get("/me/onboarding").json())["complete"]:
        seen.append((state["current"]["theme"], state["current"]["number"]))
        assert answer(c).status_code == 200
    assert len(seen) == len(qa.QUESTIONS) == 15
    assert [n for _, n in seen] == list(range(1, 16))
    assert {t for t, _ in seen} == set(qa.THEMES.values())


def test_progress_resumes_where_the_user_left_off():
    store = MemoryStore()
    c = client(store)
    consent(c)
    for _ in range(4):
        answer(c)
    later = client(store)  # a new session, same user
    state = later.get("/me/onboarding").json()
    assert state["answered"] == 4 and state["current"]["id"] == qa.QUESTIONS[4].id


def test_a_short_answer_gets_exactly_one_follow_up():
    model = Asker()
    c = client(model=model)
    consent(c)
    first = qa.QUESTIONS[0].id
    state = answer(c, "Beach.").json()
    assert state["current"]["id"] == first and state["current"]["followup"] == "What made that week feel so good?"
    state = answer(c, "Ok.", qid=first).json()  # the follow-up's answer is taken, even if short
    assert state["current"]["id"] == qa.QUESTIONS[1].id and state["current"]["followup"] is None
    assert model.calls == 1


def test_a_long_answer_gets_no_follow_up():
    model = Asker()
    c = client(model=model)
    consent(c)
    assert answer(c).json()["current"]["id"] == qa.QUESTIONS[1].id and model.calls == 0


@pytest.mark.parametrize("reply", ["Sure! Here's a question", RuntimeError("quota"), ""])
def test_a_bad_or_failed_follow_up_falls_back_to_the_theme_template(reply):
    c = client(model=Asker(reply))
    consent(c)
    state = answer(c, "Beach.").json()
    assert state["current"]["followup"] == qa.TEMPLATE_FOLLOWUPS["life"]


def test_only_the_current_question_can_be_answered():
    c = client()
    consent(c)
    assert answer(c, qid=qa.QUESTIONS[3].id).status_code == 409
    assert c.post("/me/answers", json={"question_id": qa.QUESTIONS[0].id, "text": "   "}).status_code == 422


def test_users_do_not_see_each_others_answers():
    store = MemoryStore()
    a = client(store)
    consent(a)
    answer(a)
    b = TestClient(create_app(store, verify_token=lambda t: t, followup_model=lambda: None),
                   headers={"Authorization": "Bearer user-2"})
    assert b.get("/me/onboarding").json()["answered"] == 0 and b.get("/me/onboarding").json()["consent"] is None


def test_consent_to_an_older_text_must_be_given_again(monkeypatch):
    store = MemoryStore()
    c = client(store)
    consent(c)
    monkeypatch.setattr(qa, "CONSENT_VERSION", "newer")
    assert c.get("/me/onboarding").json()["consent"] is None
    assert answer(c, qid=qa.QUESTIONS[0].id).status_code == 403


def test_a_repeated_submit_cannot_overwrite_an_answer():
    c = client()
    consent(c)
    first = qa.QUESTIONS[0].id
    assert answer(c, LONG, qid=first).status_code == 200
    assert answer(c, "A different answer entirely, sent by a double click.", qid=first).status_code == 409


def test_a_follow_up_pending_does_not_count_as_answered():
    c = client(model=Asker())
    consent(c)
    assert answer(c, "Beach.").json()["answered"] == 0


def test_the_answer_limit_is_shared_with_the_screen():
    c = client()
    consent(c)
    assert c.get("/me/onboarding").json()["max_chars"] == qa.MAX_CHARS
    too_long = "x" * (qa.MAX_CHARS + 1)
    assert c.post("/me/answers", json={"question_id": qa.QUESTIONS[0].id, "text": too_long}).status_code == 422
