"""Fuzzing the text cleaners: whatever a model writes, cleaning never crashes, never returns more than
one capped line, and never lets stage directions, speaker labels or its own name through."""
import random

import pytest

from garden.concordia_twins import MAX_LINE_CHARS, _clean_speech, echoes, parse_reflection
from garden.immersion import breaking_phrase, strip_framing

PIECES = ['"', "“", "”", "'", "*", "**", "[", "]", "(", ")", "{", "}", "{{", "}}", ":", ",", ".", "!", "?", "…",
          "\n", "  ", "Lina", "Lina:", "Lina,", "Ren B.", "Ren B.,", "she says", "he whispered softly", "Answer:",
          "Sure, I'll respond as Lina.", "Here is Lina's reflection:", "Actually, let me make it shorter:",
          "Ratings: longing=5; trust=3", "I study law", "naïve café ☕", "\t", "—", "*She pauses.*",
          "[leans in]", "(after a pause", "Private Reflection for Day 4:", "word " * 30]


def noise(rng: random.Random) -> str:
    return "".join(rng.choice(PIECES) + rng.choice(["", " "]) for _ in range(rng.randint(0, 40)))


@pytest.mark.parametrize("seed", range(20))
def test_speech_cleaning_survives_anything(seed):
    rng = random.Random(seed)
    for _ in range(250):
        alias = rng.choice(["Lina", "Ren B.", "Amir"])
        line = _clean_speech(alias, noise(rng))
        assert isinstance(line, str) and len(line) <= MAX_LINE_CHARS + 1
        assert "\n" not in line and "*" not in line and "[" not in line
        assert not line.startswith((f"{alias}:", f"{alias},")), line


@pytest.mark.parametrize("seed", range(10))
def test_reflections_framing_and_checks_survive_anything(seed):
    rng = random.Random(seed)
    for _ in range(250):
        raw = noise(rng)
        text, ratings = parse_reflection("Lina", raw)
        assert isinstance(text, str) and isinstance(ratings, dict) and len(text) <= 601
        assert isinstance(strip_framing(raw), str)
        breaking_phrase(raw)
        echoes(raw, [noise(rng), ""])


def test_ratings_still_parse_after_noise():
    text, ratings = parse_reflection("Lina", "Lina's Private Reflection for Day 2: A long day.\nRatings: longing=7; trust=4; on_my_mind=Felix")
    assert ratings == {"longing": 7, "trust": 4, "on_my_mind": "Felix"} and text == "A long day."
