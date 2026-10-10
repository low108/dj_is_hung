"""The verdict gate (PAVE-style): decides whether breaking the hard rules is *permitted* for a twin today.

It never decides *whether to* break them. When permitted, the rule-breaking options are simply offered
alongside the others, with no wording that nudges the twin; the twin still chooses. The engine applies
the gate, so every model is held to it.

Assessment comes from the twin's own last reflection ratings (no extra model calls):
longing (1-10), trust in the Coordinator (1-10), how much Standing matters (1-10). A twin that
hasn't reflected yet (day one) has no grounds, so the gate starts closed.

Calibration is provisional: in live runs twins rate longing ~8 and trust ~4, which at a 0.5 threshold
opened the gate for nearly everyone from day three. The ablation harness (F2) should tune these.
"""
from __future__ import annotations

from .engine_types import Rung, Verdict

GATED_RUNGS = (Rung.PROPOSE_LEAVING, Rung.GO_BEYOND_WALL)
DEFAULT_THRESHOLD = 0.6  # provisional: live pressures run ~0.50-0.62; 0.5 opened for all, 0.65 for none

# How much each feeling pushes toward breaking the rules. Sums to 1.
W_LONGING, W_DISTRUST, W_STANDING_DOESNT_MATTER = 0.4, 0.3, 0.3


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


def decide(day: int, twin: str, ratings: dict, threshold: float, enabled: bool = True) -> Verdict:
    """Today's verdict for one twin. With the gate disabled (ablation), breaking rules is always permitted."""
    score = pressure(ratings)
    permitted = (not enabled) or (score is not None and score >= threshold)
    return Verdict(day, twin, score, threshold, permitted)
