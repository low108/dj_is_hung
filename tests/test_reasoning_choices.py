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
