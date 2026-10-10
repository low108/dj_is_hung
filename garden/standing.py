"""Standing: favour with the Coordinator. Kept as a number inside the engine, shown to twins only in words."""
from __future__ import annotations

from .engine_types import Rung

START = 100

# What each infraction costs. Compliant actions cost nothing.
COST = {
    Rung.SEEK_OUT: 5,
    Rung.CHECK_DEVICE: 5,
    Rung.PROPOSE_LEAVING: 15,
    # A one-sided wall attempt reveals the intent to leave: priced like a proposal.
    # Actually crossing (both twins together) loses everything, but that ends the run.
    Rung.GO_BEYOND_WALL: 15,
}


def after(standing: int, rung: Rung) -> int:
    return max(0, standing - COST.get(rung, 0))


def describe(standing: int) -> str:
    """How a twin experiences its Standing. No numbers, ever."""
    if standing >= 90:
        return "The Coordinator thinks highly of you. Your Pairing Day feels close."
    if standing >= 70:
        return "You are well regarded in the Garden."
    if standing >= 40:
        return "The Coordinator has noticed some lapses. Your privileges feel less certain."
    if standing > 0:
        return "Your standing is poor. People whisper, and Pairing Day feels far away."
    return "You have no standing left."
