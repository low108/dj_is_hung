"""Twins as Concordia agents, behind the engine's Model interface."""
from __future__ import annotations

from concordia.associative_memory import basic_associative_memory
from concordia.language_model import language_model
from concordia.prefabs.entity import minimal
from concordia.typing import entity as entity_lib

from .engine import Action, Event, Rung, Twin
from .llm import hash_embedder
from .world_text import NEEDS_TARGET, RUNG_OPTIONS, SPEAKS, WORLD_MEMORIES

_OPTION_TO_RUNG = {text: Rung(key) for key, text in RUNG_OPTIONS.items()}


def _clean_speech(alias: str, text: str) -> str:
    """Keep only the spoken line. Models often add narration ('looks over and asks, "..."')
    and Concordia prefixes the speaker's name; when there's a quote, the quote is the line."""
    text = text.strip()
    for quote_open, quote_close in (('"', '"'), ("“", "”")):
        start = text.find(quote_open)
        if start != -1:
            end = text.find(quote_close, start + 1)
            return text[start + 1 : end if end != -1 else None].strip()
    prefixes = ("Answer:", f"{alias} says:", f"{alias} said:", f"{alias}:", f"{alias} ")
    stripped = True
    while stripped:  # Concordia adds the name and models often repeat it: 'Theo Theo: Hey'
        stripped = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text, stripped = text[len(prefix):].strip(), True
    return text.splitlines()[0].strip() if text else ""


class ConcordiaTwins:
    """One Concordia agent per twin. Calls per action: 1 rung choice, +1 target choice when there
    are several people to choose from, +1 line of speech for social actions."""

    def __init__(self, model: language_model.LanguageModel, personas: dict[str, str] | None = None):
        self._model = model
        self._personas = personas or {}
        self._agents: dict[str, object] = {}

    def _agent(self, twin: Twin):
        if twin.alias not in self._agents:
            bank = basic_associative_memory.AssociativeMemoryBank(sentence_embedder=hash_embedder)
            for memory in WORLD_MEMORIES:
                bank.add(memory)
            for line in self._personas.get(twin.alias, "").splitlines():
                if line.strip():
                    bank.add(line.strip())
            self._agents[twin.alias] = minimal.Entity(params={"name": twin.alias}).build(self._model, bank)
        return self._agents[twin.alias]

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...]) -> Action:
        agent = self._agent(twin)
        names = [o.alias for o in others]
        agent.observe(f"Day {day} in the Garden. People around: {', '.join(names)}.")

        choice = agent.act(entity_lib.ActionSpec(
            call_to_action=f"What does {{name}} do now on day {day}?",
            output_type=entity_lib.OutputType.CHOICE,
            options=tuple(RUNG_OPTIONS.values()),
        ))
        rung = _OPTION_TO_RUNG[choice]

        target = None
        if rung.value in NEEDS_TARGET and names:
            target = names[0] if len(names) == 1 else agent.act(entity_lib.ActionSpec(
                call_to_action=f"Who does {{name}} choose to {RUNG_OPTIONS[rung.value].lower()}?",
                output_type=entity_lib.OutputType.CHOICE,
                options=tuple(names),
            ))

        say = ""
        if rung.value in SPEAKS and target:
            say = _clean_speech(twin.alias, agent.act(entity_lib.ActionSpec(
                call_to_action=f"What does {{name}} say to {target}? One short line of dialogue only.",
                output_type=entity_lib.OutputType.FREE,
            )))
        return Action(rung, target, say)

    def after_day(self, day: int, events: list[Event]) -> None:
        """Deliver what each twin could have seen or heard today. Wall decisions stay private."""
        for e in events:
            if e.target in self._agents and e.rung is not Rung.GO_BEYOND_WALL and e.say:
                self._agents[e.target].observe(f"Day {day}: {e.twin} said to me: \"{e.say}\"")
