"""D1: twins from the Columbia Speed Dating dataset."""
import pandas as pd
import pytest

from garden import speed_dating as sd

ANSWER_KEY_FIELDS = ["dec", "dec_o", "match", "like", "prob", "attr", "attr_o", "like_o", "pid", "partner",
                     "satis_2", "you_call", "them_cal", "date_3", "attr1_2", "attr1_3", "income", "zipcode"]


def fake_dates() -> pd.DataFrame:
    base = {f: None for f in sd.PRE_DATE_FIELDS}
    base |= {"iid": 7, "gender": 0, "wave": 2, "age": 26.0, "field": "Social Work", "career": "Counselor",
             "from": "Ohio", "goal": 4.0, "date": 5.0, "go_out": 2.0, "imprace": 2.0, "imprelig": 8.0,
             "hiking": 9.0, "reading": 10.0, "clubbing": 2.0, "gaming": 1.0, "yoga": 5.0,
             "attr1_1": 10.0, "sinc1_1": 35.0, "intel1_1": 25.0, "fun1_1": 15.0, "amb1_1": 5.0, "shar1_1": 10.0,
             "attr3_1": 6.0, "sinc3_1": 9.0, "intel3_1": 8.0, "fun3_1": 5.0, "amb3_1": 7.0}
    leaked = {f: 1 for f in ANSWER_KEY_FIELDS}
    return pd.DataFrame([base | leaked | {"pid": 30}, base | leaked | {"pid": 31}])


def test_profile_reads_only_pre_date_fields():
    p = sd.profile(fake_dates(), 7)
    assert set(p) <= set(sd.PRE_DATE_FIELDS)
    assert not set(p) & set(ANSWER_KEY_FIELDS)


def test_every_template_memory_cites_real_source_fields():
    p = sd.profile(fake_dates(), 7)
    memories = sd.template_memories(p)
    assert len(memories) >= 8
    for m in memories:
        assert m.source
        assert all(src in sd.PRE_DATE_FIELDS for src in m.source.split(","))


def test_memories_say_what_the_data_says():
    text = sd.build_twin(fake_dates(), 7).persona_text()
    assert "Social Work" in text and "Counselor" in text
    assert "serious relationship" in text
    assert "reading" in text and "hiking" in text
    assert "sincere" in text  # top partner preference
    assert "religion" in text  # imprelig 8


def test_twin_gets_an_alias():
    twin = sd.build_twin(fake_dates(), 7)
    assert twin.alias and twin.gender == "f"


def test_unknown_participant_raises():
    with pytest.raises(KeyError):
        sd.profile(fake_dates(), 999)


def test_rewrites_without_a_valid_source_or_with_invented_numbers_are_rejected():
    facts = [sd.Memory("I am 26 years old.", "age"), sd.Memory("I love reading.", "reading")]
    items = [
        {"memory": "I'm twenty-six and curious.", "source": "age"},       # kept
        {"memory": "I read 50 books a year.", "source": "reading"},       # invented number: rejected
        {"memory": "I own a boat.", "source": "boat"},                    # unknown source: rejected
        {"memory": "I like cats."},                                       # no source: rejected
    ]
    kept = sd.validate_rewrite(items, facts)
    assert [(m.text, m.source) for m in kept] == [("I'm twenty-six and curious.", "age")]


class StubModel:
    def __init__(self, reply):
        self.reply = reply

    def sample_text(self, prompt, **kw):
        return self.reply


def test_llm_rewrite_falls_back_to_the_template_fact_when_rejected():
    facts = [sd.Memory("I am 26 years old.", "age"), sd.Memory("I love reading.", "reading")]
    reply = '[{"memory": "I\'m 26.", "source": "age"}, {"memory": "I read 50 books.", "source": "reading"}]'
    out = sd.rewrite_memories(facts, StubModel(reply))
    assert [m.text for m in out] == ["I'm 26.", "I love reading."]


def test_garbage_llm_reply_keeps_all_template_facts():
    facts = [sd.Memory("I am 26 years old.", "age")]
    assert sd.rewrite_memories(facts, StubModel("sorry, no")) == facts


@pytest.mark.skipif(not sd.DEFAULT_PATH.exists(), reason="speed dating CSV not downloaded")
def test_a_twin_can_be_built_for_every_real_participant():
    dates = sd.load()
    for iid in dates["iid"].unique():
        twin = sd.build_twin(dates, int(iid))
        assert all(m.source for m in twin.memories)
