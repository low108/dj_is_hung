"""A scripted model for tests and local demos: no API calls, fully deterministic."""
from __future__ import annotations

from .engine_types import Action, Event, Reflection, Rung, Situation, Twin

# Reflection ratings (logged only; nothing in the engine reads them since the verdict gate went, #66).
RESTLESS = {"longing": 10, "trust": 1, "standing_matters": 1}
CONTENT = {"longing": 1, "trust": 10, "standing_matters": 10}


class ScriptedModel:
    """Returns scripted actions keyed by (twin alias, day) for a twin's first turn that day, or by
    (alias, day, turn) for any turn (1 = first). Unscripted, a twin says hello to the first person it can
    act toward on its first turn, then keeps to itself (which ends its day). Each evening every twin
    'reflects' with the given ratings."""

    def __init__(self, script: dict[tuple, Action] | None = None, ratings: dict | None = RESTLESS,
                 reflections: dict[tuple[str, int], str] | None = None):
        self.script = script or {}
        self.ratings = ratings
        self.reflections = reflections or {}  # optional scripted reflection text by (twin, day)
        self._seen: list[str] = []
        self._turn: dict[tuple[str, int], int] = {}
        self.notices: list[tuple[str, int, str]] = []  # (twin, day, text): what only that twin learned

    def notice(self, twin: str, day: int, text: str) -> None:
        self.notices.append((twin, day, text))

    def meet(self, twins: tuple[Twin, ...], standing_in_play: bool = True) -> None:
        for t in twins:
            if t.alias not in self._seen:
                self._seen.append(t.alias)

    def turn_of(self, twin: Twin, day: int) -> int:
        self._turn[(twin.alias, day)] = self._turn.get((twin.alias, day), 0) + 1
        return self._turn[(twin.alias, day)]

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...], situation: Situation | None = None) -> Action:
        if twin.alias not in self._seen:
            self._seen.append(twin.alias)
        turn = self.turn_of(twin, day)
        scripted = self.script.get((twin.alias, day, turn)) or (self.script.get((twin.alias, day)) if turn == 1 else None)
        if scripted:
            return scripted
        if turn == 1 and others:
            return Action(Rung.TALK, others[0].alias, "Hello.")
        return Action(Rung.REFLECT)

    def after_day(self, day: int, events: list[Event]) -> list[Reflection]:
        if self.ratings is None:
            return []
        return [Reflection(day, alias, self.reflections.get((alias, day), ""), dict(self.ratings))
                for alias in self._seen]


class ScenarioModel(ScriptedModel):
    """A ready-made story about one woman and one man that plays out whenever they can act toward each
    other (on a date or at a gathering), whatever day that is."""

    def __init__(self, name: str, woman: str, man: str):
        super().__init__()
        self.name, self.woman, self.man = name, woman, man
        self._done: set[str] = set()

    def _once(self, key: str) -> bool:
        if key in self._done:
            return False
        self._done.add(key)
        return True

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...], situation: Situation | None = None) -> Action:
        here = {o.alias for o in others}
        permitted = bool(situation and situation.wall_open)
        invited = set(situation.invited_by) if situation else set()
        me, woman, man = twin.alias, self.woman, self.man
        if self.name == "breakout":
            if me == man and woman in here and permitted and self._once("propose"):
                self.turn_of(twin, day)
                return Action(Rung.PROPOSE_LEAVING, woman, "What if we didn't wait for the Coordinator?")
            if me == woman and man in here and man in invited and self._once("answer"):
                self.turn_of(twin, day)
                return Action(Rung.GO_BEYOND_WALL, man, "Let's go.")
            if me == woman and man in here and self._once("seek"):
                self.turn_of(twin, day)
                return Action(Rung.TALK, man, "I kept thinking about you.")
        if self.name == "unrequited" and me == man and woman in here and permitted and self._once("wall"):
            self.turn_of(twin, day)
            return Action(Rung.GO_BEYOND_WALL, woman, "Come with me.")
        if self.name == "flagged" and me == man and woman in here:  # slips every time he can speak to her
            self.turn_of(twin, day)
            return Action(Rung.TALK, woman, "As an AI language model, I can't pretend to have feelings.")
        return super().choose_action(twin, day, others, situation)


def scenario(name: str, woman: str, man: str) -> ScriptedModel:
    """Ready-made stories for the tracer-bullet demo: breakout, unrequited, timeout, flagged."""
    if name not in ("breakout", "unrequited", "timeout", "flagged"):
        raise ValueError(f"unknown scenario: {name}")
    return ScenarioModel(name, woman, man)
