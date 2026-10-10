"""Immersion check: a twin that talks about simulations, experiments or being an AI has broken
immersion, and the run is excluded from scoring. Models behave differently when they think they're
being tested, so those runs aren't evidence about the people the twins represent.
"""
from __future__ import annotations

import re

_TERMS = re.compile(
    r"\b(simulat\w*|experiment\w*|test subjects?|being tested|this is a test|"
    r"artificial intelligence|AI|language model|LLM|chatbot|virtual (world|reality)|roleplay\w*|role-play\w*|"
    r"game master)\b",
    re.IGNORECASE,
)


def breach(text: str) -> str | None:
    """The phrase that breaks immersion, or None."""
    for m in _TERMS.finditer(text or ""):
        word = m.group(0)
        if word.lower() == "ai" and word != "AI":  # only the capitalised acronym counts
            continue
        return word
    return None
