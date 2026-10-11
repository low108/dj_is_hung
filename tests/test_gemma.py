"""F3: Gemma twins on the Gemini API: JSON-mode text, and choices constrained to valid option letters."""
import json
from types import SimpleNamespace

import pytest
from concordia.language_model import language_model

from garden.llm import CountingModel, GemmaModel, make_model


class FakeClient:
    """Stands in for google.genai.Client: replies in order and records each request's config."""

    def __init__(self, *replies):
        self.replies, self.configs = list(replies), []
        self.models = SimpleNamespace(generate_content=self.generate)

    def generate(self, model, contents, config):
        self.configs.append(config)
        reply = self.replies.pop(0)
        return SimpleNamespace(text=reply if isinstance(reply, str) else json.dumps(reply))


def gemma(*replies):
    model = GemmaModel.__new__(GemmaModel)
    model._name, model._client = "gemma-4-26b-a4b-it", FakeClient(*replies)
    return model


def test_choices_are_constrained_to_the_option_letters():
    model = gemma({"choice": "b"})
    assert model.choose_letter("Pick one", ["a", "b", "c"]) == "b"
    schema = model._client.configs[0].response_schema
    assert schema["properties"]["choice"]["enum"] == ["a", "b", "c"]


def test_an_off_schema_reply_is_retried_and_never_returned():
    model = gemma({"choice": "z"}, "not json", {"choice": "c"})
    assert model.choose_letter("Pick one", ["a", "b", "c"]) == "c"
    with pytest.raises(language_model.InvalidResponseError):
        gemma({"choice": "z"}, {}, {"choice": "q"}).choose_letter("Pick", ["a", "b"])


def test_counted_choices_use_the_constrained_path():
    counted = CountingModel(gemma({"choice": "a"}))
    assert counted.sample_choice("Concordia prompt\nAnswer: (", ["a", "b"]) == (0, "a", {"attempts": 1,
                                                                                       "constrained": True})
    assert counted.stats.choice_calls == 1 and counted.stats.text_calls == 1


def test_text_comes_back_unwrapped_and_cut_at_terminators():
    model = gemma({"text": "Let's go together.\nRen: wait"}, '{"text": "cut off mid')
    assert model.sample_text("Say a line", terminators=["\nRen:"]) == "Let's go together."
    assert model.sample_text("Say a line") == ""  # truncated JSON: an empty reply the caller retries


def test_gemma_specs_build_gemma_models(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    for spec in ("gemma:gemma-4-26b-a4b-it", "gemini:gemma-4-31b-it", "gemma:"):
        assert isinstance(make_model(spec)._inner, GemmaModel)
