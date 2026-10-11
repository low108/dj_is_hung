"""Immersion check (#64): a twin slips out of character when the model speaks as itself (an AI, a
language model, a roleplay it was asked to do, a request it refuses). Models behave differently when
they think they're being tested, so such text never reaches anyone: a line that slips becomes that twin
keeping to itself for the turn, and a reflection that slips is dropped. The run goes on; a twin that
slips again and again flags the run for review instead of quietly being scored.

In-world unease is not a slip. In a walled Garden where a Coordinator decides everything, a twin wondering
whether any of this is real, or whether they're all being tested, is the very doubt that leads to the
wall. Harmless model framing ("I'll respond as Lina, …", "Here is Lina's reflection: …", a bracketed tag)
is stripped and the rest kept.
"""
from __future__ import annotations

import re

_PHRASES = re.compile(
    r"\b("
    r"artificial intelligence|language model|chatbot|role-?play\w*|game master|NPCs?"
    r"|(?:i'?m|i am|we'?re|we are) (?:just )?(?:an? )?(?:bots?|programs?|robots?)"
    r"|(?:experiment|scenario|exercise|prompt|task|story) (?:asking|that asks) me to"
    r"|(?:i'?m|i am) (?:being )?asked to (?:play|act|pretend|portray|write as)"
    r"|i (?:cannot|can'?t|won'?t) (?:fulfill|complete|continue|comply|do) (?:this|that|the|your)"
    r"|fictional (?:character|scenario|setting)"
    # The model talking about the prompt instead of speaking: 'What does Ravi say to Lina?" but then
    # provides "Observation: ...', '[lists feelings ... ending with a question]', 'Wait, let me ref...'
    r"|what does \w+(?: [A-Z]\.)? say to|observation:|one or two sentences(?: of dialogue)?"
    r"|in \w+(?: [A-Z]\.)?'s own words|without repeating \w+|ending with a question"
    r"|(?:wait|actually|hmm),? let me (?:ref\w*|rephrase|rewrite|redo|revise|try again)"
    r")\b",
    re.IGNORECASE,
)
# Acronyms, case-sensitive: never "Kai", "Mai" or "said".
_ACRONYMS = re.compile(r"\bAI\b|\bA\.I\.")

# Model framing around otherwise good text: removed, not counted as a slip.
_FRAMING = (
    # "Sure, I'll respond as Lina, writing her private reflection at the end of Day 6."
    re.compile(r"^\s*(?:(?:sure|okay|ok|certainly|alright)[,!.]?\s*)?(?:i'?ll|i will|let me|i'?m going to)\s+"
               r"(?:respond|reply|answer|write|speak)\b[^.:\n]*[.:]\s*", re.IGNORECASE),
    # "Certainly. Here is Lina's private reflection at the end of Day 12:"
    re.compile(r"^\s*(?:(?:sure|okay|ok|certainly|alright|of course)[,!.]?\s*)?(?:here (?:is|are)|here'?s)\b"
               r"(?:[^.:\n]|(?<= [A-Z])\.){0,80}?\b(?:reflection|response|reply|answer|line|entry|journal)\b"
               r"[^.:\n]*[.:]\s*",  # (an initial's full stop, as in "Ren B.", doesn't end it)
               re.IGNORECASE),
    # Headings: "Lina's Private Reflection for Day 1", "Ravi's Private Journal — End of Day 3", "Private Entry"
    # (a bare word counts only before a day or a colon: "Entry to the hall was closed" stays)
    re.compile(r"^\s*(?:(?:[A-Z][\w.]*(?: [A-Z]\.)?'s\s+(?:private\s+)?|private\s+)(?:reflection|journal|entry|diary)"
               r"|(?:reflection|journal|entry|diary)(?=\s*(?:for\s+)?(?:[-—–:]|(?:the\s+)?(?:end of\s+)?day\s+\w)))"
               r"(?:\s*(?:for|[-—–:])?\s*(?:the\s+)?(?:end of\s+)?day\s+\w+)?\s*[-—–:.]?\s*", re.IGNORECASE),
    # "[day5privatewriting]"
    re.compile(r"\[[^\]\n]{0,40}\]\s*"),
)


def strip_framing(text: str) -> str:
    """The text without the model's framing around it."""
    text = text or ""
    changed = True
    while changed:
        before = text
        for pattern in _FRAMING:
            text = pattern.sub("", text, count=1)
        changed = text != before
    return text.strip()


def breaking_phrase(text: str) -> str | None:
    """The phrase in `text` that shows the model speaking as itself, or None."""
    if m := _PHRASES.search(text or "") or _ACRONYMS.search(text or ""):
        return m.group(0)
    return None
