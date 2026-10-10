"""Language models for twins: Gemini/Gemma via Concordia, wrapped to count calls and time."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np
from concordia.language_model import language_model

FLASH = "gemini-3.5-flash"  # 3.8-flash returned 503 (overloaded) on 2026-10-10
PRO = "gemini-3.1-pro-preview"
GEMMA = "gemma-4-31b-it"


@dataclass
class CallStats:
    text_calls: int = 0
    choice_calls: int = 0
    prompt_chars: int = 0
    output_chars: int = 0
    seconds: float = 0.0
    retries: int = 0

    def as_dict(self) -> dict:
        return {
            "text_calls": self.text_calls,
            "retries": self.retries,
            "choice_calls": self.choice_calls,
            "prompt_chars": self.prompt_chars,
            "output_chars": self.output_chars,
            "approx_prompt_tokens": self.prompt_chars // 4,
            "approx_output_tokens": self.output_chars // 4,
            "model_seconds": round(self.seconds, 1),
        }


class CountingModel(language_model.LanguageModel):
    """Counts every underlying text sample (choice retries included) and the time spent."""

    def __init__(self, inner: language_model.LanguageModel, *, letter_choices: bool = True,
                 requests_per_minute: int | None = None):
        """letter_choices: answer choices with our own counted letter prompt instead of the inner model's
        sample_choice (whose internal calls we couldn't count). Set False for offline test models.
        requests_per_minute: client-side pacing for rate-limited keys (the free tier allows 5/min/model)."""
        self._inner = inner
        self._letter_choices = letter_choices
        self._rpm = requests_per_minute
        self._sent: list[float] = []
        self.stats = CallStats()
        self._lock = threading.Lock()

    def _pace(self) -> None:
        if not self._rpm:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._sent = [t for t in self._sent if now - t < 60]
                if len(self._sent) < self._rpm:
                    self._sent.append(now)
                    return
                wait = 60 - (now - self._sent[0]) + 0.5
            time.sleep(wait)

    def sample_text(self, prompt: str, **kwargs) -> str:
        for attempt in range(6):
            self._pace()
            start = time.perf_counter()  # model time excludes pacing and backoff waits
            try:
                out = self._inner.sample_text(prompt, **kwargs)
                break
            except Exception as e:  # overloads (503) and rate limits (429) are temporary
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if code not in (429, 500, 503) or attempt == 5:
                    raise
                with self._lock:
                    self.stats.retries += 1
                time.sleep(60 if code == 429 else min(2 ** attempt, 30))
        with self._lock:
            self.stats.text_calls += 1
            self.stats.prompt_chars += len(prompt)
            self.stats.output_chars += len(out)
            self.stats.seconds += time.perf_counter() - start
        return out

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        with self._lock:
            self.stats.choice_calls += 1
        if self._letter_choices:
            return language_model_choice(self, prompt, responses, seed=seed)
        return self._inner.sample_choice(prompt, responses, seed=seed)


def language_model_choice(model: CountingModel, prompt: str, responses: Sequence[str], *, seed=None):
    """Concordia's prompt already lists the options by letter and ends with 'Answer: ('; `responses`
    are those letters. Sample a short continuation and take the first valid letter, retrying a few times."""
    sample = ""
    for attempt in range(5):
        sample = model.sample_text(prompt, max_tokens=8, temperature=0.5 + 0.1 * attempt)
        for ch in sample.strip().lower():
            if ch in responses:
                i = responses.index(ch)
                return i, responses[i], {"attempts": attempt + 1}
    raise language_model.InvalidResponseError(f"no valid choice in: {sample!r}")


class GenAIModel(language_model.LanguageModel):
    """Gemini or Gemma through the Google Gen AI SDK, with thinking kept minimal: twins make quick,
    in-the-moment choices, and thinking tokens would cost time and count against max_tokens."""

    def __init__(self, model_name: str, api_key: str | None = None):
        from google import genai

        self._name = model_name
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])

    def sample_text(self, prompt: str, *, max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
                    terminators: Collection[str] = (), temperature: float = 1.0, **kwargs) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            max_output_tokens=max(max_tokens, 64),
            temperature=temperature,
            stop_sequences=list(terminators)[:5] or None,
        )
        if self._name.startswith("gemini-3"):
            config.thinking_config = types.ThinkingConfig(thinking_level="low")
        elif self._name.startswith("gemini-2.5"):
            config.thinking_config = types.ThinkingConfig(thinking_budget=0 if "pro" not in self._name else 128)
        response = self._client.models.generate_content(model=self._name, contents=prompt, config=config)
        return response.text or ""  # blocked or empty replies come back as "" and are retried by the caller

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        raise NotImplementedError("wrap in CountingModel, which answers choices by letter")


def gemini(model_name: str = FLASH, requests_per_minute: int | None = None) -> CountingModel:
    rpm = requests_per_minute or int(os.environ.get("GEMINI_RPM", "0")) or None
    return CountingModel(GenAIModel(model_name), requests_per_minute=rpm)


def hash_embedder(text: str, dim: int = 256) -> np.ndarray:
    """Cheap, deterministic bag-of-words embedding for memory retrieval (no API calls)."""
    vec = np.zeros(dim, dtype=np.float32)
    for word in text.lower().split():
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


class KeywordModel(language_model.LanguageModel):
    """Offline test model: picks the first option containing a keyword scripted for the current prompt."""

    def __init__(self, picks: dict[str, str] | None = None, say: str = "Hello."):
        self.picks = picks or {}  # prompt substring -> option substring
        self.say = say

    def sample_text(self, prompt: str, *, max_tokens: int = 0, terminators: Collection[str] = (), **kw) -> str:
        return self.say

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        # Only look at the question being asked now, not earlier ones in the transcript.
        question = prompt[prompt.rfind("Question:"):]
        options = {}
        for line in question.splitlines():
            line = line.strip()
            if len(line) > 3 and line[0] == "(" and line[2] == ")":
                options[line[1]] = line[4:]
        for needle, pick in self.picks.items():
            if needle in question:
                for letter, text in options.items():
                    if pick in text and letter in responses:
                        return responses.index(letter), letter, {}
        # Default: the first option as listed in Concordia's original order isn't knowable here,
        # so prefer a plain, compliant action when it's offered.
        for letter, text in options.items():
            if text.startswith("Spend time talking") and letter in responses:
                return responses.index(letter), letter, {}
        return 0, responses[0], {}
