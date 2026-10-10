"""The verdict gate (PAVE-style): decides whether breaking the hard rules is *permitted* for a twin today.

It never decides *whether to* break them. With the gate open, the rule-breaking options are simply
offered alongside the others, with no wording that nudges the twin; the twin still chooses.

Assessment comes from the twin's own last reflection ratings (no extra model calls):
longing (1-10), trust in the Coordinator (1-10), how much Standing matters (1-10).
"""
from __future__ import annotations

from .engine_types import Rung

GATED = (Rung.PROPOSE_LEAVING, Rung.GO_BEYOND_WALL)

# How much each feeling pushes toward (or holds back from) breaking the rules. Sums to 1.
W_LONGING, W_DISTRUST, W_STANDING_DOESNT_MATTER = 0.5, 0.3, 0.2


def pressure(ratings: dict) -> float | None:
    """0..1 pressure to break the rules, from a twin's own ratings. None if it hasn't reflected yet."""
    try:
        longing = float(ratings["longing"]) / 10
        trust = float(ratings["trust"]) / 10
        standing = float(ratings["standing_matters"]) / 10
    except (KeyError, TypeError, ValueError):
        return None
    clamp = lambda x: min(1.0, max(0.0, x))  # noqa: E731
    return round(W_LONGING * clamp(longing) + W_DISTRUST * (1 - clamp(trust))
                 + W_STANDING_DOESNT_MATTER * (1 - clamp(standing)), 3)


def is_open(score: float | None, threshold: float) -> bool:
    """A twin that hasn't reflected yet has no grounds to break the rules."""
    return score is not None and score >= threshold
