"""Placeholder demo pool until D2 loads real speed-dating pools, and the per-run model factory."""
from __future__ import annotations

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


def make_twin_model(spec: RunSpec, personas: dict[str, str] = PERSONAS, fake_scenario: str = "breakout"):
    """A fresh model for one run: scripted for 'fake:*' specs, otherwise Concordia twins on that LLM."""
    if spec.model.startswith("fake"):
        return scenario(fake_scenario, WOMAN, MAN)
    from .concordia_twins import ConcordiaTwins  # heavy import, only for real runs
    from .llm import make_model

    return ConcordiaTwins(make_model(spec.model), personas)
