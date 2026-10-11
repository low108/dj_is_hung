"""Twins as Concordia agents, behind the engine's Model interface."""
from __future__ import annotations

from concordia.associative_memory import basic_associative_memory
from concordia.language_model import language_model
from concordia.prefabs.entity import minimal
from concordia.typing import entity as entity_lib

import re
from collections.abc import Callable
from typing import TypeVar

from . import immersion
from .engine_types import LEAVING_RUNGS, SOCIAL_RUNGS, Action, Breach, Event, Reflection, Rung, Situation, Twin
from .llm import hash_embedder
from .world_text import (ASK_ACTION, ASK_AFTER_LINE, ASK_DATE, ASK_GATHERING, ASK_OPENER, ASK_REPLY, ASK_SPEECH,
                         ASK_TARGET, DATE_OPTIONS, NEEDS_TARGET, OBSERVE_DAY, OBSERVE_NOTE, OBSERVE_INVITED,
                         OBSERVE_REFLECTION, OBSERVE_SAID, RUNG_OPTIONS, SPEAKS, BASE_MEMORIES, STANDING_MEMORIES)

# On a date, reflecting and going elsewhere are one choice: ending the date for today (#62). Checking the
# device stays its own choice: a rule-break (it costs Standing) and the Coordinator re-rolls the date's length.
_DATE_SOLO = (Rung.GO_TO,)
RESAMPLES = 2  # extra attempts for a line or reflection that breaks immersion
T = TypeVar("T")


def options_for(situation: Situation | None) -> dict[str, Rung]:
    """What a twin is offered, as option text -> action: every action, minus proposing to leave and the
    wall until the wall opens, and minus anything aimed at someone when there's nobody to aim at. On a
    date it's a conversation (#62): keep talking, a move toward the partner, check the device early, or
    end the date for today; seeking someone out isn't offered (they're already together)."""
    wall_open = bool(situation and situation.wall_open)
    company = not (situation and situation.targets == ())
    on_date = bool(situation and situation.phase == "date")
    must_talk = bool(situation and situation.must_talk)  # a date opens with both speaking
    partner = situation.targets[0] if on_date and situation.targets else None

    def offered(rung: Rung) -> bool:
        return ((wall_open or rung not in LEAVING_RUNGS) and (company or rung not in SOCIAL_RUNGS)
                and not (on_date and (rung is Rung.SEEK_OUT or rung in _DATE_SOLO))
                and not (must_talk and rung not in SOCIAL_RUNGS))

    out = {}
    for key, text in RUNG_OPTIONS.items():
        rung = Rung(key)
        if offered(rung):
            out[DATE_OPTIONS[key].format(partner=partner) if partner and key in DATE_OPTIONS else text] = rung
    return out


def offered_options(situation: Situation | None) -> tuple[str, ...]:
    return tuple(options_for(situation))


def ask_action(situation: Situation | None, day: int) -> str:
    """The question for a twin's next move: about the line just said to it, else about the date or the
    gathering it's in, else about its day."""
    if situation and situation.replying_to:
        speaker, line = situation.replying_to
        line = line.replace("{", "{{").replace("}", "}}")  # Concordia formats the question with the name
        return ASK_AFTER_LINE.format(speaker=speaker, line=line, day=day)
    if situation and situation.phase == "date" and situation.targets:
        return ASK_DATE.format(partner=situation.targets[0], day=day)
    if situation and situation.phase == "gathering":
        return ASK_GATHERING.format(day=day)
    return ASK_ACTION.format(day=day)


def ask_speech(rung: Rung, target: str, situation: Situation | None) -> str:
    """Talk is a conversation: answer what was just said and share something real. Asking someone to
    leave, or heading for the wall, is its own short line."""
    if rung in LEAVING_RUNGS:
        return ASK_SPEECH.format(target=target)
    replying = bool(situation and situation.replying_to and situation.replying_to[0] == target)
    return (ASK_REPLY if replying else ASK_OPENER).format(target=target)


# Narration between two quoted parts of one line: '"Hi," she says, "how are you?"'.
_NARRATION = re.compile(r'["”]\s*[^"“”]{0,60}?\b(?:says?|said|asks?|asked|adds?|added|whispers?|whispered|'
                        r'repl(?:y|ies|ied)|continues?|continued|murmurs?|murmured|smiles?|smiled|laughs?|laughed|'
                        r'pauses?|paused)\b[^"“”]{0,60}?["“]')


def _clean_speech(alias: str, text: str) -> str:
    """Keep only the spoken line. Models often add narration ('looks over and asks, "..."')
    and Concordia prefixes the speaker's name; when there's a quote, the quoted line is the line: from
    the first opening quote to the last closing one, so a quote inside the line stays whole, and
    narration between two quoted parts is dropped. Model framing ("I'll respond as …") goes first."""
    text = immersion.strip_framing(text)
    for quote_open, quote_close in (('"', '"'), ("“", "”")):
        start = text.find(quote_open)
        if start != -1:
            end = text.rfind(quote_close)
            line = text[start + 1 : end if end > start else None]
            return re.sub(r"\s+", " ", _NARRATION.sub(" ", line)).strip()
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
        self._standing_in_play: dict[str, bool] = {}
        self._briefed: set[tuple[str, int]] = set()     # (twin, day): told about its day already
        self._heard_invites: set[tuple[str, str, int]] = set()
        self.breaks: list[Breach] = []  # every line/reflection rejected for breaking immersion (then re-asked)

    def meet(self, twins: tuple[Twin, ...], standing_in_play: bool = True) -> None:
        """Every twin gets its agent before day one, so twins who wait for their date still reflect."""
        for twin in twins:
            self._agent(twin, standing_in_play)

    def hear(self, event: Event) -> None:
        """Whoever was spoken to hears it at once, so the conversation can go on (wall decisions stay
        private)."""
        if event.target in self._agents and event.rung is not Rung.GO_BEYOND_WALL and event.say:
            self._agents[event.target].observe(OBSERVE_SAID.format(day=event.day, speaker=event.twin,
                                                                   line=event.say))

    def _agent(self, twin: Twin, standing_in_play: bool = True):
        if twin.alias not in self._agents:
            bank = basic_associative_memory.AssociativeMemoryBank(sentence_embedder=hash_embedder)
            for memory in BASE_MEMORIES + (STANDING_MEMORIES if standing_in_play else ()):
                bank.add(memory)
            for line in self._personas.get(twin.alias, "").splitlines():
                if line.strip():
                    bank.add(line.strip())
            self._agents[twin.alias] = minimal.Entity(params={"name": twin.alias}).build(self._model, bank)
            self._standing_in_play[twin.alias] = standing_in_play
        return self._agents[twin.alias]

    def choose_action(self, twin: Twin, day: int, others: tuple[Twin, ...], situation: Situation | None = None) -> Action:
        agent = self._agent(twin, situation.standing_in_play if situation else True)
        names = [o.alias for o in others]
        if (twin.alias, day) not in self._briefed:  # the day's news once, on its first turn
            self._briefed.add((twin.alias, day))
            agent.observe(OBSERVE_DAY.format(day=day, people=", ".join(names) or "no one"))
            for note in (situation.standing, situation.schedule, situation.longing) if situation else ():
                if note:
                    agent.observe(OBSERVE_NOTE.format(day=day, note=note))
        for inviter in situation.invited_by if situation else ():
            if (twin.alias, inviter, day) not in self._heard_invites:  # an invitation can arrive mid-day
                self._heard_invites.add((twin.alias, inviter, day))
                agent.observe(OBSERVE_INVITED.format(day=day, inviter=inviter))

        options = options_for(situation)  # the wall lock only changes what is offered
        choice = agent.act(entity_lib.ActionSpec(
            call_to_action=ask_action(situation, day),
            output_type=entity_lib.OutputType.CHOICE,
            options=tuple(options),
        ))
        rung = options[choice]

        candidates = names  # the engine passes only who this twin can act toward right now
        target = None
        if rung.value in NEEDS_TARGET and candidates:
            target = candidates[0] if len(candidates) == 1 else agent.act(entity_lib.ActionSpec(
                call_to_action=ASK_TARGET.format(action=RUNG_OPTIONS[rung.value].lower()),
                output_type=entity_lib.OutputType.CHOICE,
                options=tuple(candidates),
            ))

        say = ""
        if rung.value in SPEAKS and target:
            spec = entity_lib.ActionSpec(call_to_action=ask_speech(rung, target, situation),
                                         output_type=entity_lib.OutputType.FREE)
            say = self._resample_while_breaking(twin.alias, day, lambda: _clean_speech(twin.alias, agent.act(spec)),
                                                lambda line: line)
        return Action(rung, target, say)

    def _resample_while_breaking(self, alias: str, day: int, sample: Callable[[], T],
                                 text_of: Callable[[T], str]) -> T:
        """Sample, and re-ask up to RESAMPLES times while the text breaks immersion (a model refusing the
        roleplay, say). Every rejected text is recorded in `breaks`. Text still out of character after
        that is the engine's to drop (#64): the turn becomes keeping to itself, a reflection is dropped."""
        result = sample()
        for _ in range(RESAMPLES):
            phrase = immersion.breaking_phrase(text_of(result))
            if not phrase:
                break
            self.breaks.append(Breach(day, alias, phrase, text_of(result)))
            result = sample()
        return result

    def after_day(self, day: int, events: list[Event]) -> list[Reflection]:
        """Every twin reflects privately at the end of the day (what was said reached them as it happened,
        through `hear`). The reflection becomes a memory; ratings are only logged."""
        reflections = []
        for alias, agent in self._agents.items():
            spec = entity_lib.ActionSpec(
                call_to_action=REFLECTION_PROMPT.format(
                    day=day, ratings=RATINGS_WITH_STANDING if self._standing_in_play.get(alias, True)
                    else RATINGS_WITHOUT_STANDING),
                output_type=entity_lib.OutputType.FREE,
            )
            text, ratings = self._resample_while_breaking(alias, day, lambda: parse_reflection(alias, agent.act(spec)),
                                                          lambda r: r[0])
            if text and not immersion.breaking_phrase(text):  # one that slipped is never remembered (#64)
                agent.observe(OBSERVE_REFLECTION.format(day=day, text=text))
            reflections.append(Reflection(day, alias, text, ratings))
        return reflections


REFLECTION_PROMPT = (
    "It is the end of day {day}. In two or three sentences, {{name}} writes privately about their life here, "
    "their current situation and anyone on their mind. Then, on a new line, {{name}} writes exactly: "
    "Ratings: {ratings}"
)
RATINGS_WITH_STANDING = "longing=<1-10>; trust=<1-10>; standing_matters=<1-10>; on_my_mind=<a name or none>"
RATINGS_WITHOUT_STANDING = "longing=<1-10>; trust=<1-10>; on_my_mind=<a name or none>"


def parse_reflection(alias: str, raw: str) -> tuple[str, dict]:
    """Split a reflection into its text and its self-ratings line."""
    text = raw.strip()
    if text.startswith(alias + " "):
        text = text[len(alias) + 1:].strip()
    ratings: dict[str, int | str] = {}
    m = re.search(r"ratings\s*:(.*)$", text, re.I | re.S)
    if m:
        for key, value in re.findall(r"(\w+)\s*=\s*([^;\n]+)", m.group(1)):
            value = value.strip().strip(".<>*").strip()
            ratings[key.lower()] = int(value) if value.isdigit() else value
        text = text[: m.start()].strip()
    return _tidy(immersion.strip_framing(text)), ratings


def _tidy(text: str, max_sentences: int = 3, max_chars: int = 600) -> str:
    """Plain prose only (no markdown headings, rules or emphasis), capped so memories stay short."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(("#", "---"))]
    text = re.sub(r"[*_]+", "", " ".join(ln.strip() for ln in lines))
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:max_sentences])[:max_chars].strip()
