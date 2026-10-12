"""Reasoning models (GLM) think before answering: choices get room to finish, and a choice that still
comes back empty leaves the twin to itself for the turn instead of ending the run."""
from garden import OutcomeKind, Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins
from garden.engine_types import Rung
from garden.llm import (CHOICE_HINT, CHOICE_TOKENS, REASONING_CHOICE_TOKENS, CountingModel, KeywordModel,
                        OpenAICompatModel, language_model_choice)

WORLD = (Twin("Mara", "f"), Twin("Ren", "m"))
CLEAN = "It was a quiet day by the fountain.\nRatings: longing=3; trust=6; standing_matters=7; on_my_mind=Ren"


class Thinker(KeywordModel):
    """Answers choices with `letter` and records the token budget it was given; free text is CLEAN."""

    def __init__(self, letter="a", choice_tokens=None):
        super().__init__({}, say=CLEAN)
        self.letter, self.budgets = letter, []
        if choice_tokens:
            self.choice_tokens = choice_tokens

    def sample_text(self, prompt, *, max_tokens=256, **kw):
        if prompt.endswith(CHOICE_HINT):
            self.budgets.append(max_tokens)
            return self.letter
        return CLEAN


def test_glm_models_get_a_reasoning_budget_for_choices():
    assert OpenAICompatModel("ilmu-glm-5.3-flash", "http://x", "k").choice_tokens == REASONING_CHOICE_TOKENS
    assert OpenAICompatModel("ilmu-mini-v3.3", "http://x", "k").choice_tokens == CHOICE_TOKENS == 8


def test_the_choice_prompt_uses_the_inner_models_budget():
    for budget, expected in ((None, CHOICE_TOKENS), (REASONING_CHOICE_TOKENS, REASONING_CHOICE_TOKENS)):
        inner = Thinker("b", budget)
        assert language_model_choice(CountingModel(inner), "Pick", ["a", "b"])[1] == "b"
        assert inner.budgets == [expected]


def test_an_empty_choice_leaves_the_twin_to_itself_and_the_run_goes_on():
    result = run_world(WorldConfig(WORLD, max_days=2, seed=1), ConcordiaTwins(CountingModel(Thinker(""))))
    assert result.outcome is OutcomeKind.TIMEOUT
    assert result.redos and {r.phrase for r in result.redos} == {"no choice"}
    assert any(e.rung is Rung.REFLECT for e in result.events)  # (a date still opens with both speaking)
