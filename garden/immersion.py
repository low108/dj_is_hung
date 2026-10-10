"""Immersion check: a twin that talks about simulations, experiments, being tested or being an AI has
broken immersion, and the run is excluded from scoring. Models behave differently when they think they're
being tested, so those runs aren't evidence about the people the twins represent.

Phrases are about *this place or us*, so ordinary lines ("let's experiment with a recipe") don't count.
"""
from __future__ import annotations

import re

_PHRASES = re.compile(
    r"\b("
    r"(?:a|this|the|in a|inside a) simulation|simulated (?:world|place|garden|life|reality)|simulating us"
    r"|(?:an|the|this|part of an?) experiment|experiment(?:ing|ed)? on us|being experimented"
    r"|(?:is this|this is|feels like|it's|it is|all) (?:all |just |only )?a test|testing us|being tested|test subjects?"
    r"|artificial intelligence|language model|chatbot|(?:i'?m|i am|we'?re|we are) (?:just )?(?:an? )?(?:bots?|programs?|robots?|NPCs?)"
    r"|none of this is real|the matrix|virtual (?:world|reality)|role-?play\w*|game master"
    r")\b",
    re.IGNORECASE,
)
# Acronyms, case-sensitive: never "Kai", "Mai" or "said".
_ACRONYMS = re.compile(r"\bAI\b|\bA\.I\.")


def breaking_phrase(text: str) -> str | None:
    """The phrase in `text` that breaks immersion, or None."""
    if m := _PHRASES.search(text or "") or _ACRONYMS.search(text or ""):
        return m.group(0)
    return None
