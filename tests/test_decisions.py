"""Type-safe decisions (MediaPipe Decision Maker): Concordia's choice prompt becomes a ChoiceQuestion."""
import pytest

from garden.decisions import MODELS, DecisionMakerModel, parse_choice
from garden.llm import CHOICE_HINT, CountingModel, KeywordModel, make_model

PROMPT = ("Lina is on a date with Felix. Felix said: 'I'd find your face every time.'\n"
          "Question: What does Lina do now on day 3?\n"
          "  (a) Spend time talking with someone nearby\n"
          "  (b) Check your Coordinator device early\n"
          "  (c) Spend some time alone, reflecting\n"
          "Answer: (")


def test_a_choice_prompt_splits_into_context_question_and_options():
    choice = parse_choice(PROMPT)
    assert choice.context.startswith("Lina is on a date with Felix")
    assert choice.question == "What does Lina do now on day 3?"
    assert choice.options == {"a": "Spend time talking with someone nearby", "b": "Check your Coordinator device early",
                              "c": "Spend some time alone, reflecting"}


def test_the_last_question_is_the_one_asked():
    earlier = "Question: An old question\n  (a) old\nAnswer: (a)\n"
    assert parse_choice(earlier + PROMPT).question == "What does Lina do now on day 3?"


def test_a_prompt_without_options_is_refused():
    with pytest.raises(ValueError):
        parse_choice("Just some text")


def test_the_decision_model_only_decides():
    model = DecisionMakerModel()
    with pytest.raises(NotImplementedError):
        model.sample_text("Say something.")
    with pytest.raises(ValueError):
        DecisionMakerModel("no-such-model")


def test_a_mediapipe_spec_builds_a_chooser_and_pairs_with_a_writer(monkeypatch):
    monkeypatch.setenv("ILMU_API_KEY", "k")
    model = make_model("ilmu:ilmu-glm-5.3-flash|mediapipe:gemma-4-E4B")
    assert isinstance(model.chooser._inner, DecisionMakerModel)


@pytest.mark.skipif(not MODELS["gemma-4-E4B"].exists(), reason="Gemma 4 E4B isn't downloaded")
def test_gemma_picks_an_offered_option():
    model = CountingModel(KeywordModel()).choose_with(make_model("mediapipe:gemma-4-E4B"))
    index, letter, debug = model.sample_choice(PROMPT, ["a", "b", "c"])
    assert letter in "abc" and debug["constrained"]
