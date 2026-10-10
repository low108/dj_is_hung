"""Prompt versioning: every piece of text twins see, hashed into a short version id.

A run records the version; `save_prompt_version` writes the exact text under that id, so any logged
result can be traced back to the prompts that produced it. Change any wording and the version changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import coordinator, standing, world_text
from .longing import LONGING_WORDS


def prompt_texts() -> dict:
    from .concordia_twins import (  # imports Concordia; only needed when versioning
        RATINGS_WITH_STANDING, RATINGS_WITHOUT_STANDING, REFLECTION_PROMPT)
    from .llm import CHOICE_HINT

    return {
        "base_memories": list(world_text.BASE_MEMORIES),
        "standing_memories": list(world_text.STANDING_MEMORIES),
        "rung_options": dict(world_text.RUNG_OPTIONS),
        "templates": {k: getattr(world_text, k) for k in (
            "OBSERVE_DAY", "OBSERVE_NOTE", "OBSERVE_SAID", "OBSERVE_REFLECTION", "ASK_ACTION", "ASK_TARGET", "ASK_SPEECH")},
        "reflection_prompt": REFLECTION_PROMPT,
        "reflection_ratings": [RATINGS_WITH_STANDING, RATINGS_WITHOUT_STANDING],
        "choice_hint": CHOICE_HINT,
        # every distinct sentence the Standing bands produce, derived from the function itself
        "standing_words": sorted({standing.describe(v) for v in range(standing.START + 1)}),
        "longing_words": [words for _, words in LONGING_WORDS],
        "schedule": {k: getattr(coordinator, k) for k in (
            "SCHEDULE_PAIRED", "SCHEDULE_ONE_DAY", "SCHEDULE_DAYS", "SCHEDULE_UNASSIGNED", "SCHEDULE_GATHERING", "RUMOUR")},
    }


def prompt_version(texts: dict | None = None) -> str:
    blob = json.dumps(texts or prompt_texts(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def save_prompt_version(directory: Path) -> str:
    """Write prompts/<version>.json (once) and return the version."""
    texts = prompt_texts()
    version = prompt_version(texts)
    path = Path(directory) / f"{version}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(texts, indent=2, ensure_ascii=False))
    return version
