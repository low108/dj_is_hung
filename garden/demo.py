"""Placeholder demo pool until D2 loads real speed-dating pools, and the per-run model factory."""
from __future__ import annotations

import os

from .batch import RunSpec
from .engine_types import Twin
from .fake_model import scenario

PERSONAS = {
    "Mara": "I'm a nurse. I follow rules, but I'll bend them for people I love.\nI want a home and a family one day.",
    "Ren": "I'm an engineer. I own my mistakes, even when it costs me.\nFamily dinners matter to me.",
    "Jun": "I love travel and freedom. I keep my options open.",
    "Theo": "I'm kind and steady. I want to live out of a backpack, no kids.",
    "Kai": "I like order. I avoid arguments and never break rules.",
    "Sam": "When I fall for someone, I fall hard. I get jealous easily.",
}
WOMAN, MAN = "Mara", "Ren"  # MAN is who the scripted fake scenarios use
POOL = tuple(Twin(n, "f" if n == WOMAN else "m") for n in PERSONAS)
MEN = [t.alias for t in POOL if t.alias != WOMAN]

FAKE_MODELS = ["fake:a", "fake:b", "fake:c"]  # three stand-ins for the three-model ensemble (F4)


def is_fake(model: str) -> bool:
    """Scripted stand-in (no API calls), as opposed to "provider:model"."""
    return model.startswith("fake")


def make_twin_model(spec: RunSpec, personas: dict[str, str] = PERSONAS, fake_scenario: str = "breakout",
                    woman: str = WOMAN):
    """A fresh model for one run: scripted for 'fake:*' specs, otherwise Concordia twins on that LLM."""
    if is_fake(spec.model):
        return scenario(fake_scenario, woman, MAN)
    from .concordia_twins import ConcordiaTwins  # heavy import, only for real runs
    from .llm import make_model

    return ConcordiaTwins(make_model(spec.model), personas)


def make_highlight_model(models: list[str]):
    """The model that captions highlights (C3): HIGHLIGHT_MODEL if set, else Gemini Flash when a Gemini
    key is set, else the simulation's first real model. None for an all-scripted simulation: highlights
    then use template captions, so scripted runs never make API calls."""
    if all(is_fake(m) for m in models):
        return None
    from .llm import FLASH, make_model

    default = f"gemini:{FLASH}" if os.environ.get("GEMINI_API_KEY") else next(m for m in models if not is_fake(m))
    return make_model(os.environ.get("HIGHLIGHT_MODEL") or default)


def make_followup_model():
    """Asks onboarding follow-ups (D3): Gemini Flash when GEMINI_API_KEY is set (FOLLOWUP_MODEL overrides),
    else None and the theme's template follow-up is used."""
    spec = os.environ.get("FOLLOWUP_MODEL")
    if not spec and not os.environ.get("GEMINI_API_KEY"):
        return None
    from .llm import FLASH, make_model

    return make_model(spec or f"gemini:{FLASH}")


def with_her_twin(alias: str, persona: str, threshold: float):
    """The demo pool's men with a user's own twin as the woman (D4)."""
    from .pools import PoolSetup

    men = tuple(t for t in POOL if t.alias != WOMAN)
    personas = {t.alias: PERSONAS[t.alias] for t in men} | {alias: persona}
    return PoolSetup((Twin(alias, "f"), *men), personas, alias, MEN, None, ((alias, threshold),))


def make_extraction_model():
    """The Pro-tier model that builds twins (D4): EXTRACTION_MODEL if set, else Gemini Pro when a Gemini
    key is set, else ILMU (development). None when no model is configured."""
    from .llm import PRO, make_model

    spec = os.environ.get("EXTRACTION_MODEL")
    if not spec and os.environ.get("GEMINI_API_KEY"):
        spec = f"gemini:{PRO}"
    if not spec and os.environ.get("ILMU_API_KEY"):
        spec = "ilmu:ilmu-mini-v3.3"
    return (spec, make_model(spec)) if spec else None
