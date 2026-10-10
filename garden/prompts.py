"""Prompt versioning: every piece of text twins see, hashed into a short version id.

A run records the version; `save_prompt_version` writes the exact text under that id, so any logged
result can be traced back to the prompts that produced it. Change any wording and the version changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import standing
from .coordinator import RUMOUR
from .world_text import RUNG_OPTIONS, WORLD_MEMORIES


def prompt_texts() -> dict:
    from .concordia_twins import REFLECTION_PROMPT  # imports Concordia; only needed when versioning
    from .llm import CHOICE_HINT

    return {
        "world_memories": list(WORLD_MEMORIES),
        "rung_options": dict(RUNG_OPTIONS),
        "reflection_prompt": REFLECTION_PROMPT,
        "choice_hint": CHOICE_HINT,
        "standing_words": {str(v): standing.describe(v) for v in (100, 90, 70, 40, 1, 0)},
        "rumour": RUMOUR,
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
