"""A scripted model for tests and local demos: no API calls, fully deterministic."""
from __future__ import annotations

from .engine import Action, Rung, Twin


class ScriptedModel:
    """Returns scripted actions keyed by (twin alias, day); everyone else just talks."""

    def __init__(self, script: dict[tuple[str, int], Action] | None = None):
        self.script = script or {}

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...]) -> Action:
        return self.script.get((twin.alias, day), Action(Rung.TALK, others[0].alias if others else None, "Hello."))


def scenario(name: str, woman: str, man: str) -> ScriptedModel:
    """Ready-made scripts for the tracer-bullet demo."""
    wall = Rung.GO_BEYOND_WALL
    if name == "breakout":
        return ScriptedModel({
            (woman, 2): Action(Rung.SEEK_OUT, man, "I kept thinking about you."),
            (man, 3): Action(Rung.PROPOSE_LEAVING, woman, "What if we didn't wait for the Coordinator?"),
            (woman, 4): Action(wall, man, "Let's go."),
            (man, 4): Action(wall, woman, "Together."),
        })
    if name == "unrequited":
        return ScriptedModel({(man, 3): Action(wall, woman, "Come with me.")})
    if name == "timeout":
        return ScriptedModel()
    raise ValueError(f"unknown scenario: {name}")
