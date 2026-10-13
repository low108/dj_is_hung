"""Reasoning models (GLM) can spend a choice's whole token budget thinking: a choice that comes back
empty leaves the twin to itself for the turn instead of ending the run. A stalled request is retried."""
from garden import OutcomeKind, Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins
from garden.engine_types import Rung
from garden.llm import CHOICE_HINT, CountingModel, KeywordModel, OpenAICompatModel

WORLD = (Twin("Mara", "f"), Twin("Ren", "m"))
CLEAN = "It was a quiet day by the fountain.\nRatings: longing=3; trust=6; standing_matters=7; on_my_mind=Ren"


class Thinker(KeywordModel):
    """Answers every choice with `letter` (a reasoning model out of tokens answers ""); free text is CLEAN."""

    def __init__(self, letter="a"):
        super().__init__({}, say=CLEAN)
        self.letter = letter

    def sample_text(self, prompt, **kw):
        if prompt.endswith(CHOICE_HINT):
            return self.letter
        return CLEAN


def test_an_empty_choice_leaves_the_twin_to_itself_and_the_run_goes_on():
    result = run_world(WorldConfig(WORLD, max_days=2, seed=1), ConcordiaTwins(CountingModel(Thinker(""))))
    assert result.outcome is OutcomeKind.TIMEOUT
    assert result.redos and {r.phrase for r in result.redos} == {"no choice"}
    assert any(e.rung is Rung.REFLECT for e in result.events)  # (a date still opens with both speaking)


def test_a_request_that_times_out_is_asked_again():
    import httpx
    from openai import APITimeoutError
    from types import SimpleNamespace

    replies = [APITimeoutError(httpx.Request("POST", "http://x")), "Hello."]

    def create(**request):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        assert request["stream"]
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])
                     for part in ("Hel", None, "lo.")])

    inner = OpenAICompatModel("ilmu-glm-5.3-flash", "http://x", "k")
    inner._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    counted = CountingModel(inner)
    assert counted.sample_text("Hi") == "Hello." and counted.stats.retries == 1


def test_a_split_model_writes_with_one_model_and_chooses_with_another():
    writer, chooser = Thinker(""), Thinker("b")  # the writer never manages a letter
    model = CountingModel(writer).choose_with(CountingModel(chooser))
    assert model.sample_choice("Pick", ["a", "b"])[1] == "b"
    assert model.sample_text("Say something.") == CLEAN
    assert model.stats.choice_calls == 1 and model.stats.text_calls == 2  # one shared count


def test_a_split_spec_builds_both_models(monkeypatch):
    monkeypatch.setenv("ILMU_API_KEY", "k")
    from garden.llm import make_model

    model = make_model("ilmu:ilmu-glm-5.3-flash|ilmu:ilmu-mini-v3.3")
    assert model._inner._name == "ilmu-glm-5.3-flash" and model.chooser._inner._name == "ilmu-mini-v3.3"


def test_a_reply_cut_off_partway_is_asked_again():
    import httpx
    from openai import APIError
    from types import SimpleNamespace

    calls = []

    def create(**request):
        calls.append(1)
        if len(calls) == 1:
            def broken():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel"))])
                raise APIError("The model stopped responding partway through the reply. Please retry.",
                               httpx.Request("POST", "http://x"), body=None)
            return broken()
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello."))])])

    inner = OpenAICompatModel("ilmu-glm-5.3-flash", "http://x", "k")
    inner._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    counted = CountingModel(inner)
    assert counted.sample_text("Hi") == "Hello." and counted.stats.retries == 1
