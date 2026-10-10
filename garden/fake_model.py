"""A scripted model for tests and local demos: no API calls, fully deterministic."""
from __future__ import annotations

from .engine_types import Action, Event, Reflection, Rung, Situation, Twin

# Feelings strong enough to open the verdict gate (from day two, after the first reflection).
RESTLESS = {"longing": 10, "trust": 1, "standing_matters": 1}
CONTENT = {"longing": 1, "trust": 10, "standing_matters": 10}


class ScriptedModel:
    """Returns scripted actions keyed by (twin alias, day); everyone else just talks.
    Each evening every twin 'reflects' with the given ratings, which feed the verdict gate."""

    def __init__(self, script: dict[tuple[str, int], Action] | None = None, ratings: dict | None = RESTLESS):
        self.script = script or {}
        self.ratings = ratings
        self._seen: list[str] = []

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...], situation: Situation | None = None) -> Action:
        if twin.alias not in self._seen:
            self._seen.append(twin.alias)
        return self.script.get((twin.alias, day), Action(Rung.TALK, others[0].alias if others else None, "Hello."))

    def after_day(self, day: int, events: list[Event]) -> list[Reflection]:
        if self.ratings is None:
            return []
        return [Reflection(day, alias, "", dict(self.ratings)) for alias in self._seen]


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
