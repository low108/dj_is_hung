"""Type-safe decisions with MediaPipe Decision Maker (Google AI Edge) running Gemma 4 E4B on this machine.

A twin's choice becomes a ChoiceQuestion: the options it is offered are the criteria and everything it
knows (persona, diary, the people it has met, today) is the context. The Decision Maker scores every
option in one pass, with no text generated, so the answer is always one of the offered options: never
empty, never a stray letter (GLM spent its whole token budget reasoning and returned nothing).

Model: gemma-4-E4B-it.litertlm from huggingface.co/litert-community/gemma-4-E4B-it-litert-lm (3.66 GB,
Apache-2.0), saved under data/models/ (git-ignored). On the GPU a decision takes 0.2-0.7 s; on the CPU
4-13 s. One model is loaded per process and shared by every run (loading takes ~20 s).
"""
from __future__ import annotations

import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from concordia.language_model import language_model

from .paths import DATA_DIR

MODELS = {"gemma-4-E4B": DATA_DIR / "models" / "gemma-4-E4B-it.litertlm"}
DEFAULT = "gemma-4-E4B"
MAX_TOKENS = 4096
CONTEXT_CHARS = 12_000  # ~3,000 tokens of the most recent context, leaving room for the question

_OPTION = re.compile(r"^\s+\(([a-z])\) (.+)$")


@dataclass(frozen=True)
class Choice:
    """A Concordia multiple-choice prompt taken apart: what the twin knows, what it is asked, its options."""

    context: str
    question: str
    options: dict[str, str]  # letter -> option text


def parse_choice(prompt: str) -> Choice:
    """Concordia writes '...context...Question: <q>\\n  (a) <option>\\n  (b) <option>\\nAnswer: ('."""
    head, sep, tail = prompt.rpartition("Question: ")
    if not sep:
        raise ValueError("not a multiple-choice prompt (no 'Question: ')")
    lines = tail.split("\n")
    options = {m.group(1): m.group(2).strip() for line in lines[1:] if (m := _OPTION.match(line))}
    if not options:
        raise ValueError("multiple-choice prompt with no options")
    return Choice(head.strip()[-CONTEXT_CHARS:], lines[0].strip(), options)


_makers: dict[str, object] = {}
_lock = threading.Lock()  # one shared model; MediaPipe tasks are not safe to call from several threads


def _maker(name: str):
    """The process's Decision Maker for `name`, loaded once: on the GPU, else the CPU."""
    from mediapipe.tasks.python.core import base_options
    from mediapipe.tasks.python.decision import decision_maker as dm

    if name not in _makers:
        path = MODELS[name]
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing: download it from "
                                    f"https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm")
        last: Exception | None = None
        for delegate in (base_options.BaseOptions.Delegate.GPU, base_options.BaseOptions.Delegate.CPU):
            try:
                _makers[name] = dm.DecisionMaker.create_from_options(dm.DecisionMakerOptions(
                    base_options=base_options.BaseOptions(model_asset_path=str(path), delegate=delegate),
                    max_num_tokens=MAX_TOKENS))
                break
            except Exception as e:  # no GPU here: the CPU works everywhere, only slower
                last = e
        else:
            raise RuntimeError(f"could not load {path}") from last
    return _makers[name]


class DecisionMakerModel(language_model.LanguageModel):
    """Answers choices only (wrap in CountingModel and pair it with a writer: 'writer|mediapipe:...')."""

    def __init__(self, name: str = DEFAULT):
        if name not in MODELS:
            raise ValueError(f"unknown decision model {name!r}; known: {sorted(MODELS)}")
        self.name = name
        self.last: dict[str, float] = {}  # the probabilities behind the latest choice (option text -> p)

    def guided_letter(self, prompt: str, letters: Sequence[str], temperature: float = 0.0) -> str:
        """The offered letter the Decision Maker scores highest. CountingModel calls this for choices."""
        from mediapipe.tasks.python.decision import decision_maker as dm

        from .llm import CHOICE_HINT

        choice = parse_choice(prompt.removesuffix(CHOICE_HINT))
        criteria = {letter: choice.options[letter] for letter in letters if letter in choice.options}
        question = dm.ChoiceQuestion(criteria=criteria, instructions=choice.question, normalize_prior=True)
        with _lock:
            result = _maker(self.name).evaluate_choice(choice.context, question)
        self.last = {criteria[k]: round(p, 3) for k, p in result.probabilities.items()}
        return result.selected_key

    def sample_text(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("the Decision Maker only decides: pair it with a writer ('writer|mediapipe:...')")

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        raise NotImplementedError("wrap in CountingModel, which uses guided_letter")
