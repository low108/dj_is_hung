"""Twin extraction and review (D4): one Pro-tier call with a JSON schema turns a user's Q&A answers into
a twin: about 30 first-person seed memories (each tagged with the part of life it's about), an
attachment style, values, dealbreakers, and a rebelliousness score with the answers that justify it.

The user reviews the twin as its memories grouped by section, in the twin's own (first-person) words,
and can rewrite any section. A rewritten section replaces that section's extracted memories, so edits
always override the extraction. The twin is known to others only by an anonymous alias.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from . import onboarding as qa

Section = Literal["life", "past", "conflict", "dealbreakers", "rules"]
SECTIONS: dict[str, str] = {
    "life": "How I live",
    "past": "Love and the past",
    "conflict": "When we disagree",
    "dealbreakers": "What I won't accept",
    "rules": "Rules and risk",
}
TARGET_MEMORIES = 30

# Anonymous aliases: not the demo pool's names, not the user's. Chosen from the user id, so stable.
ALIASES = ("Aster", "Briar", "Calla", "Dahlia", "Elowen", "Fern", "Hazel", "Iris", "Juniper", "Lark",
           "Linnea", "Marigold", "Nell", "Odette", "Poppy", "Quinn", "Rowan", "Saffron", "Tamsin", "Willa")


class Memory(BaseModel):
    section: Section
    text: str = Field(description="One first-person sentence, as the person would remember it.")


class Extraction(BaseModel):
    memories: list[Memory] = Field(description=f"About {TARGET_MEMORIES} first-person seed memories.")
    attachment_style: Literal["secure", "anxious", "avoidant", "fearful-avoidant"]
    values: list[str] = Field(description="3 to 6 short phrases.")
    dealbreakers: list[str] = Field(description="1 to 5 short phrases.")
    rebelliousness: float = Field(ge=0, le=1, description="0 = never breaks rules, 1 = breaks them readily.")
    rebelliousness_evidence: list[str] = Field(description="Ids of the answers that justify the score.")


PROMPT = """You are building an AI twin of a person from their own interview answers, for a dating simulation.

Write about {n} seed memories in the FIRST PERSON, one sentence each, as this person would remember or
say them: who they are, what they value, how they have loved, how they fight and make up, what they
won't accept, and how they feel about rules and risk. Tag each with the section it belongs to:
life, past, conflict, dealbreakers, rules. Stay faithful to the answers; don't invent facts.
Never name other people; say "my ex", "my sister" and so on.

Also give their attachment style, values, dealbreakers, and a rebelliousness score from 0 (never
breaks rules, even for love) to 1 (breaks them readily), citing the answer ids that justify it.

Interview:
{interview}"""


class ExtractionFailed(Exception):
    pass


def interview_text(answers: dict[str, dict]) -> str:
    lines = []
    for q in qa.QUESTIONS:
        a = answers.get(q.id)
        if not a:
            continue
        lines.append(f"[{q.id}] {q.text}\nAnswer: {a['answer']}")
        if a.get("followup") and a.get("followup_answer"):
            lines.append(f"Follow-up: {a['followup']}\nAnswer: {a['followup_answer']}")
    return "\n\n".join(lines)


def extract(answers: dict[str, dict], model) -> Extraction:
    """The single structured call. Raises ExtractionFailed if the reply doesn't fit the schema."""
    prompt = PROMPT.format(n=TARGET_MEMORIES, interview=interview_text(answers))
    raw = model.sample_json(prompt, Extraction)
    try:
        extraction = Extraction.model_validate_json(_json_part(raw))
    except ValidationError as e:
        raise ExtractionFailed(f"the model's twin didn't fit the schema: {e.error_count()} problems") from e
    known = {q.id for q in qa.QUESTIONS}
    extraction.rebelliousness_evidence = [i for i in extraction.rebelliousness_evidence if i in known]
    extraction.memories = [m for m in extraction.memories if m.text.strip()]
    if not extraction.memories:
        raise ExtractionFailed("the model returned no memories")
    return extraction


def _json_part(raw: str) -> str:
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if 0 <= start < end else raw


def alias_for(uid: str) -> str:
    return ALIASES[int(hashlib.sha256(uid.encode()).hexdigest(), 16) % len(ALIASES)]


def threshold(rebelliousness: float) -> float:
    """The verdict gate's threshold: a rebel needs less pressure to cross the wall. 0.5 maps to the
    neutral 0.6 the engine uses for everyone else."""
    return round(0.8 - 0.4 * rebelliousness, 2)


def new_twin(uid: str, extraction: Extraction, model_name: str, at: str) -> dict:
    return {"alias": alias_for(uid), "built_at": at, "model": model_name,
            "extraction": extraction.model_dump(), "overrides": {}}


def sentences(text: str) -> list[str]:
    """A rewritten section, split into memories (one per sentence or line)."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def memories(twin: dict) -> list[dict]:
    """The twin's seed memories: the user's rewritten sections replace that section's extracted ones."""
    overrides = twin["overrides"]
    out = [m for m in twin["extraction"]["memories"] if m["section"] not in overrides]
    for section, texts in overrides.items():
        out += [{"section": section, "text": t, "edited": True} for t in texts]
    order = list(SECTIONS)
    return sorted(out, key=lambda m: order.index(m["section"]))


def edit(twin: dict, section: str, text: str) -> dict:
    """Rewrite one section in the user's words (empty text: back to the extraction)."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}")
    overrides = dict(twin["overrides"])
    if text.strip():
        overrides[section] = sentences(text)
    else:
        overrides.pop(section, None)
    return twin | {"overrides": overrides}


def summary(twin: dict) -> dict:
    """The plain-language review: each section as the twin's own words, plus what it was read as."""
    mems = memories(twin)
    x = twin["extraction"]
    by_name = {q.id: q.text for q in qa.QUESTIONS}
    return {
        "alias": twin["alias"],
        "sections": [{"id": s, "title": title, "text": " ".join(m["text"] for m in mems if m["section"] == s),
                      "edited": s in twin["overrides"]} for s, title in SECTIONS.items()],
        "attachment_style": x["attachment_style"],
        "values": x["values"],
        "dealbreakers": x["dealbreakers"],
        "rebelliousness": x["rebelliousness"],
        "rebelliousness_because": [by_name[i] for i in x["rebelliousness_evidence"] if i in by_name],
        "memory_count": len(mems),
    }


def persona_text(twin: dict) -> str:
    return "\n".join(m["text"] for m in memories(twin))


def dumps(extraction: Extraction) -> str:  # for scripted test models
    return json.dumps(extraction.model_dump())
