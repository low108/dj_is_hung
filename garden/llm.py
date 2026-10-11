"""Language models for twins: Gemini/Gemma via Concordia, wrapped to count calls and time."""
from __future__ import annotations

import hashlib
import json
import re
import os
import threading
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np
from concordia.language_model import language_model

FLASH = "gemini-3.5-flash"  # 3.8-flash returned 503 (overloaded) on 2026-10-10
PRO = "gemini-3.1-pro-preview"
GEMMA = "gemma-4-26b-a4b-it"  # MoE, 4B active: ~1-2s per call in JSON mode; the 31B dense model takes ~35s


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


class Pacer:
    """Client-side rate limit shared by every model using the same key: parallel runs share one quota."""

    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self._sent: list[float] = []
        self._lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._sent = [t for t in self._sent if now - t < 60]
                if len(self._sent) < self.rpm:
                    self._sent.append(now)
                    return
                delay = 60 - (now - self._sent[0]) + 0.5
            time.sleep(delay)


_PACERS: dict[tuple[str, str], Pacer] = {}
_PACERS_LOCK = threading.Lock()


def shared_pacer(key: tuple[str, str], requests_per_minute: int | None) -> Pacer | None:
    """One Pacer per (provider, model), however many runs and threads use it."""
    if not requests_per_minute:
        return None
    with _PACERS_LOCK:
        return _PACERS.setdefault(key, Pacer(requests_per_minute))


def _no_quota(error: Exception) -> bool:
    """A 429 that waiting a minute won't fix: no quota for this model on the plan (Pro on the free
    tier), or the day's quota is used up."""
    text = str(error)
    return "limit: 0" in text or "PerDay" in text


class CountingModel(language_model.LanguageModel):
    """Counts every underlying text sample (choice retries included) and the time spent."""

    def __init__(self, inner: language_model.LanguageModel, *, letter_choices: bool = True,
                 pacer: Pacer | None = None, attempts: int = 6):
        """letter_choices: answer choices with our own counted letter prompt instead of the inner model's
        sample_choice (whose internal calls we couldn't count). Set False for offline test models.
        pacer: a shared client-side rate limit (the Gemini free tier allows 5 requests/min/model)."""
        self._inner = inner
        self._letter_choices = letter_choices
        self._pacer = pacer
        self._attempts = attempts  # retries for overloads and rate limits (fewer when a user is waiting)
        self.stats = CallStats()
        self._lock = threading.Lock()

    def _pace(self) -> None:
        if self._pacer:
            self._pacer.wait()

    def sample_text(self, prompt: str, **kwargs) -> str:
        return self._counted(prompt, lambda: self._inner.sample_text(prompt, **kwargs))

    def sample_json(self, prompt: str, schema: type) -> str:
        """JSON text matching the pydantic `schema` (the inner model must support structured output)."""
        return self._counted(prompt, lambda: self._inner.sample_json(prompt, schema))

    def _counted(self, prompt: str, call) -> str:
        last = self._attempts - 1
        for attempt in range(self._attempts):
            self._pace()
            start = time.perf_counter()  # model time excludes pacing and backoff waits
            try:
                out = call()
                break
            except Exception as e:  # overloads (503) and rate limits (429) are temporary
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if code not in (429, 500, 503) or attempt == last or _no_quota(e):
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
        if self._letter_choices and hasattr(self._inner, "choose_letter"):  # guided decoding: always valid
            letter = self._counted(prompt, lambda: self._inner.choose_letter(prompt + CHOICE_HINT, responses))
            return responses.index(letter), letter, {"attempts": 1, "constrained": True}
        if self._letter_choices:
            return language_model_choice(self, prompt, responses, seed=seed)
        return self._inner.sample_choice(prompt, responses, seed=seed)


def parse_choice_letter(sample: str, letters: Sequence[str]) -> str | None:
    """Find the chosen option letter in a reply. Completion-style models answer 'b)'; chat models
    answer 'The answer is **(b) pear**'. Never pick a letter out of an ordinary word."""
    text = sample.strip().lower()
    m = re.match(r"^\W*([a-z])(?![a-z])", text)  # reply starts with the letter: 'b', 'b)', '(b)', '**b**'
    if m and m.group(1) in letters:
        return m.group(1)
    for m in re.finditer(r"\(([a-z])\)", text):  # an explicit '(b)' anywhere
        if m.group(1) in letters:
            return m.group(1)
    return None


CHOICE_TEMPERATURE = 0.5  # first attempt
CHOICE_RETRY_STEP = 0.1   # added per retry when a reply has no valid letter
TEXT_TEMPERATURE = 1.0    # speech and reflections
CHOICE_HINT = "\n(Reply with only the letter of the chosen option.)\nAnswer: ("


def language_model_choice(model: CountingModel, prompt: str, responses: Sequence[str], *, seed=None):
    """Concordia's prompt already lists the options by letter and ends with 'Answer: ('; `responses`
    are those letters. Ask for just the letter, parse it strictly, and retry a few times."""
    hinted = prompt + CHOICE_HINT
    sample = ""
    for attempt in range(5):
        sample = model.sample_text(hinted, max_tokens=8, temperature=CHOICE_TEMPERATURE + CHOICE_RETRY_STEP * attempt)
        letter = parse_choice_letter(sample, responses)
        if letter:
            return responses.index(letter), letter, {"attempts": attempt + 1}
    raise language_model.InvalidResponseError(f"no valid choice in: {sample!r}")


class GenAIModel(language_model.LanguageModel):
    """Gemini or Gemma through the Google Gen AI SDK, with thinking kept minimal: twins make quick,
    in-the-moment choices, and thinking tokens would cost time and count against max_tokens."""

    def __init__(self, model_name: str, api_key: str | None = None):
        from google import genai

        self._name = model_name
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])

    def sample_text(self, prompt: str, *, max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
                    terminators: Collection[str] = (), temperature: float = TEXT_TEMPERATURE, **kwargs) -> str:
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

    def sample_json(self, prompt: str, schema: type) -> str:
        """One call constrained to the pydantic `schema` (Gemini structured output)."""
        from google.genai import types

        config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                             temperature=TEXT_TEMPERATURE, max_output_tokens=8192)
        response = self._client.models.generate_content(model=self._name, contents=prompt, config=config)
        return response.text or ""

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        raise NotImplementedError("wrap in CountingModel, which answers choices by letter")


class GemmaModel(GenAIModel):
    """Gemma 4 on the Gemini API. It always thinks before free text (20-40s a call, and thinking can't be
    turned off), but answers JSON-mode requests directly in 1-2s. So speech and reflections come back as
    {"text": ...}, and ladder choices are constrained to an enum of the option letters: guided decoding,
    so Gemma can't return an invalid action."""

    TEXT_SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}

    def _json(self, prompt: str, schema: dict, temperature: float, max_tokens: int) -> dict:
        from google.genai import types

        config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                             temperature=temperature, max_output_tokens=max_tokens)
        response = self._client.models.generate_content(model=self._name, contents=prompt, config=config)
        try:
            data = json.loads(response.text or "{}")
        except json.JSONDecodeError:  # cut off at max_tokens: an empty reply, which callers retry
            return {}
        return data if isinstance(data, dict) else {}

    def sample_text(self, prompt: str, *, max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
                    terminators: Collection[str] = (), temperature: float = TEXT_TEMPERATURE, **kwargs) -> str:
        text = str(self._json(prompt, self.TEXT_SCHEMA, temperature, max(max_tokens + 32, 96)).get("text", ""))
        for stop in terminators:  # JSON mode has no stop sequences; cut where one would have stopped
            if stop and stop in text:
                text = text.split(stop, 1)[0]
        return text.strip()

    def sample_json(self, prompt: str, schema: type) -> str:
        return GenAIModel.sample_json(self, prompt, schema)

    def choose_letter(self, prompt: str, letters: Sequence[str]) -> str:
        schema = {"type": "OBJECT", "properties": {"choice": {"type": "STRING", "enum": list(letters)}},
                  "required": ["choice"]}
        for attempt in range(3):
            letter = self._json(prompt, schema, CHOICE_TEMPERATURE + CHOICE_RETRY_STEP * attempt, 64).get("choice")
            if letter in letters:
                return letter
        raise language_model.InvalidResponseError(f"no valid choice from {self._name}")


def _answer_only(text: str) -> str:
    """Some reasoning models put their thinking in <think> tags; keep only the answer."""
    return (text.split("</think>", 1)[1] if "</think>" in text else text).strip()


class OpenAICompatModel(language_model.LanguageModel):
    """Any OpenAI-compatible Chat Completions API (used for ILMU during development)."""

    def __init__(self, model_name: str, base_url: str, api_key: str):
        from openai import OpenAI

        self._name = model_name
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def sample_text(self, prompt: str, *, max_tokens: int = language_model.DEFAULT_MAX_TOKENS,
                    terminators: Collection[str] = (), temperature: float = TEXT_TEMPERATURE, **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=self._name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max(max_tokens, 64),
            temperature=temperature,
            stop=list(terminators)[:4] or None,
        )
        return _answer_only(response.choices[0].message.content or "")

    def sample_json(self, prompt: str, schema: type) -> str:
        """JSON mode plus the schema in the prompt (no schema enforcement here; the caller validates)."""
        import json

        spec = json.dumps(schema.model_json_schema())
        response = self._client.chat.completions.create(
            model=self._name,
            messages=[{"role": "user", "content": f"{prompt}\n\nAnswer with JSON matching this schema:\n{spec}"}],
            response_format={"type": "json_object"},
            max_tokens=8192,
            temperature=TEXT_TEMPERATURE,
        )
        return _answer_only(response.choices[0].message.content or "")

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        raise NotImplementedError("wrap in CountingModel, which answers choices by letter")


ILMU_BASE_URL = "https://api.ilmu.ai/v1"
ILMU_MINI = "ilmu-mini-v3.3"


def gemini(model_name: str = FLASH, requests_per_minute: int | None = None, attempts: int = 6) -> CountingModel:
    rpm = requests_per_minute or int(os.environ.get("GEMINI_RPM", "0")) or None
    return CountingModel(GenAIModel(model_name), pacer=shared_pacer(("gemini", model_name), rpm), attempts=attempts)


def make_model(spec: str | None = None, attempts: int = 6) -> CountingModel:
    """Build a twin model from 'provider:model', e.g. 'gemini:gemini-3.5-flash' or 'ilmu:ilmu-mini-v3.3'.
    Defaults to the TWIN_MODEL environment variable, then Gemini Flash. A bare model name means Gemini."""
    spec = spec or os.environ.get("TWIN_MODEL") or f"gemini:{FLASH}"
    provider, _, name = spec.partition(":") if ":" in spec else ("gemini", "", spec)
    if provider == "gemma" or (provider == "gemini" and name.startswith("gemma")):
        rpm = int(os.environ.get("GEMMA_RPM", "0")) or None
        model = name or GEMMA
        return CountingModel(GemmaModel(model), pacer=shared_pacer(("gemma", model), rpm), attempts=attempts)
    if provider == "gemini":
        return gemini(name or FLASH, attempts=attempts)
    if provider == "ilmu":
        rpm = int(os.environ.get("ILMU_RPM", "0")) or None
        inner = OpenAICompatModel(name or ILMU_MINI, ILMU_BASE_URL, os.environ["ILMU_API_KEY"])
        return CountingModel(inner, pacer=shared_pacer(("ilmu", name or ILMU_MINI), rpm), attempts=attempts)
    raise ValueError(f"unknown model provider {provider!r} in {spec!r}")


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
