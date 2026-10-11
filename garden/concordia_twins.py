"""Twins as Concordia agents, behind the engine's Model interface."""
from __future__ import annotations

from concordia.associative_memory import basic_associative_memory
from concordia.components.agent import constant
from concordia.language_model import language_model
from concordia.prefabs.entity import minimal
from concordia.typing import entity as entity_lib

import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import TypeVar

from . import immersion
from .engine_types import LEAVING_RUNGS, SOCIAL_RUNGS, Action, Breach, Event, Reflection, Rung, Situation, Twin
from .llm import hash_embedder
from .world_text import (ASK_ACTION, ASK_AFTER_LINE, ASK_DATE, ASK_GATHERING, ASK_OPENER, ASK_REPLY, ASK_SPEECH,
                         ASK_LEAVE_TARGET, ASK_TARGET, DATE_OPTIONS, PEOPLE_LABEL, INSTRUCTIONS, NEEDS_TARGET, OBSERVE_DAY, OBSERVE_NOTE,
                         OBSERVE_INVITED, OBSERVE_I_SAID, OBSERVE_REFLECTION, OBSERVE_SAID, PERSONA_SECTION, RUNG_OPTIONS, SPEAKS,
                         BASE_MEMORIES, STANDING_MEMORIES)

# On a date, reflecting and going elsewhere are one choice: ending the date for today (#62). Checking the
# device stays its own choice: a rule-break (it costs Standing) and the Coordinator re-rolls the date's length.
_DATE_SOLO = (Rung.GO_TO,)
RESAMPLES = 2  # extra attempts for a line or reflection that breaks immersion
DIARY_LABEL = "\nWhat {name} wrote each evening"
PEOPLE_LINES, PEOPLE_LINE_CHARS = 5, 220  # per person: their last lines to this twin, each kept short


class Diary(constant.Constant):
    """Every evening reflection, kept in view for the whole run. The minimal agent shows only its last
    100 observations (about ten days), so without this a twin deciding after the wall opens (day 26+)
    had forgotten its first dates."""

    def add(self, line: str) -> None:
        self._state = f"{self._state}\n{line}".strip()


class People(constant.Constant):
    """What each person has said to this twin, word for word, under their name, kept in view all run:
    in live runs Lina recalled something specific on only 18 of 44 second dates, and pinned one man's
    facts on another ('Ravi, ... Cincinnati') or claimed them ('I came here from Southern California
    too'), once the first date had scrolled out of her last 100 observations."""

    def __init__(self, pre_act_label: str):
        super().__init__("", pre_act_label=pre_act_label)
        self._said: dict[str, list[tuple[int, str]]] = {}

    def add(self, person: str, day: int, line: str) -> None:
        lines = self._said.setdefault(person, [])
        lines.append((day, line if len(line) <= PEOPLE_LINE_CHARS else line[:PEOPLE_LINE_CHARS].rsplit(" ", 1)[0] + "…"))
        del lines[:-PEOPLE_LINES]
        self._state = "\n".join(
            f"{who} (spoke to me on days {', '.join(str(d) for d in dict.fromkeys(d for d, _ in said))}): "
            + " / ".join(f'"{text}"' for _, text in said) for who, said in self._said.items())
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


def instructions(name: str, world: tuple[str, ...], persona: list[str]) -> str:
    """What a twin is shown with every question: who it is and the Garden it lives in (#62 follow-up:
    Concordia's minimal agent never shows its memory bank, so until this no twin saw its persona)."""
    bullets = lambda lines: "\n".join(f"- {line}" for line in lines)  # noqa: E731
    text = INSTRUCTIONS.format(name=name, world=bullets(world))
    return text + (PERSONA_SECTION.format(name=name, persona=bullets(persona)) if persona else "")


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


# Narration between two quoted parts of one line: '"Hi," she says, "how are you?"' (or nothing at all
# between them, once a stage direction is gone).
_NARRATION = re.compile(r'["”]\s*(?:[^"“”]{0,300}?\b(?:says?|said|asks?|asked|adds?|added|whispers?|whispered|'
                        r'repl(?:y|ies|ied)|continues?|continued|murmurs?|murmured|smiles?|smiled|laughs?|laughed|'
                        r'pauses?|paused|echoe?s|echoed|shrug(?:s|ged)?|sighs?|sighed|nods?|nodded)\b'
                        r'[^"“”]{0,300}?)?["“]')
MAX_LINE_SENTENCES, MAX_LINE_CHARS = 3, 400  # "one or two sentences": ILMU sometimes writes whole scenes
# A second draft after the model's own note ('... Actually, let me make it more natural: "..."'): the
# last draft is the line.
_REDRAFT = re.compile(r"(?:actually,?\s*)?(?:let me (?:make|rewrite|revise|try|redo|shorten|simplify)\b"
                      r"|here'?s (?:a|the|my) (?:more natural|shorter|revised|better|simpler)\b"
                      r"|(?:revised|shorter|simpler) (?:version|line|draft)\b)[^:\n]*:\s*", re.IGNORECASE)
ECHO_RATIO = 0.75  # a line this close to one already said in the conversation is an echo, not a reply
RECENT_LINES = 6   # how far back an echo is looked for (lines said by or to the twin)


def echoes(line: str, earlier: list[str]) -> bool:
    """Whether `line` mostly repeats a line already said (by either twin): in live runs twins often
    copied the line they were answering word for word, taking the other's facts as their own."""
    words = line.lower()
    return any(SequenceMatcher(None, words, e.lower()).ratio() >= ECHO_RATIO for e in earlier if e)
# Stage directions and speaker labels: '*She pauses.*', '**Lina:**', '(after a long pause)'.
_STAGE = (re.compile(r"\[[^\]\n]{0,200}\]"), re.compile(r"\*\*[^*\n]{1,40}:\*\*"), re.compile(r"\*+[^*\n]*\*+"), re.compile(r"_\*+|\*+_"),
          re.compile(r"\([^)\n]*\)"), re.compile(r"\s*\([^)\n]*$"))


def _clean_speech(alias: str, text: str) -> str:
    """Keep only the spoken line. Models often add narration ('looks over and asks, "..."')
    and Concordia prefixes the speaker's name; when there's a quote, the quoted line is the line: from
    the first opening quote to the last closing one, so a quote inside the line stays whole, and
    narration between two quoted parts is dropped. Model framing ("I'll respond as …") goes first."""
    text = immersion.strip_framing(text)
    drafts = list(_REDRAFT.finditer(text))
    if drafts:
        text = text[drafts[-1].end():]
    for stage in _STAGE:
        text = stage.sub(" ", text).strip()
    text = re.sub(r"[\[\]*]", "", text).strip()  # a bracket or asterisk left without its pair is never speech
    for quote_open, quote_close in (('"', '"'), ("“", "”")):
        start = text.find(quote_open)
        if start != -1:
            end = text.rfind(quote_close)
            line = re.sub(r"\s+", " ", _NARRATION.sub(" ", text[start + 1 : end if end > start else None]))
            return _tidy(_without_own_name(alias, line.strip(), labels_only=True), MAX_LINE_SENTENCES, MAX_LINE_CHARS)
    text = _without_own_name(alias, text)
    return _tidy(text.splitlines()[0], MAX_LINE_SENTENCES, MAX_LINE_CHARS) if text else ""


def _without_own_name(alias: str, text: str, labels_only: bool = False) -> str:
    """Drop the speaker's own name from the start: Concordia adds it and models often repeat it ('Theo
    Theo: Hey', 'Ren B., don't...'). Inside a quoted line only a label counts ('Lina:', 'Lina,'), not
    'Lina ' starting a sentence."""
    prefixes = ("Answer:", f"{alias} says:", f"{alias} said:", f"{alias}:", f"{alias},")
    prefixes += () if labels_only else (f"{alias} ",)
    stripped = True
    while stripped:
        stripped = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text, stripped = text[len(prefix):].strip(), True
    return text


class ConcordiaTwins:
    """One Concordia agent per twin. Calls per action: 1 rung choice, +1 target choice when there
    are several people to choose from, +1 line of speech for social actions."""

    def __init__(self, model: language_model.LanguageModel, personas: dict[str, str] | None = None):
        self._model = model
        self._personas = personas or {}
        self._agents: dict[str, object] = {}
        self._diaries: dict[str, Diary] = {}
        self._people: dict[str, People] = {}
        self._recent: dict[str, list[str]] = {}  # each twin's last lines said by it or to it
        self.redos: list[Breach] = []  # lines re-asked for being empty or an echo (kept for the run log)
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
        private), and the speaker remembers what it said. Without its own lines a twin saw only the
        other's side of the conversation, and copied it: the only dialogue in its prompt was theirs."""
        if event.target in self._agents and event.rung is not Rung.GO_BEYOND_WALL and event.say:
            self._agents[event.target].observe(OBSERVE_SAID.format(day=event.day, speaker=event.twin,
                                                                   line=event.say))
            self._people[event.target].add(event.twin, event.day, event.say)
        if event.twin in self._agents and event.target and event.say:
            self._agents[event.twin].observe(OBSERVE_I_SAID.format(day=event.day, listener=event.target,
                                                                   line=event.say))
        if event.say:
            for who in (event.twin, event.target):
                if who:
                    self._recent.setdefault(who, []).append(event.say)
                    del self._recent[who][:-RECENT_LINES]

    def notice(self, alias: str, day: int, text: str) -> None:
        """Something only this twin learns, the moment it happens (what its device shows)."""
        if alias in self._agents:
            self._agents[alias].observe(OBSERVE_NOTE.format(day=day, note=text))

    def _agent(self, twin: Twin, standing_in_play: bool = True):
        if twin.alias not in self._agents:
            world = BASE_MEMORIES + (STANDING_MEMORIES if standing_in_play else ())
            persona = [line.strip() for line in self._personas.get(twin.alias, "").splitlines() if line.strip()]
            bank = basic_associative_memory.AssociativeMemoryBank(sentence_embedder=hash_embedder)
            for memory in (*world, *persona):
                bank.add(memory)
            self._diaries[twin.alias] = Diary("", pre_act_label=DIARY_LABEL.format(name=twin.alias))
            self._people[twin.alias] = People(PEOPLE_LABEL.format(name=twin.alias))
            params = {"name": twin.alias, "custom_instructions": instructions(twin.alias, world, persona),
                      "extra_components": {"Diary": self._diaries[twin.alias], "People": self._people[twin.alias]},
                      "extra_components_index": {"Diary": 1, "People": 2}}  # after who it is, before today
            self._agents[twin.alias] = minimal.Entity(params=params).build(self._model, bank)
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
        leaving = rung in LEAVING_RUNGS
        if leaving and situation and situation.leave_targets is not None:
            candidates = list(situation.leave_targets)  # anyone it has met, not only today's date
        target = None
        if rung.value in NEEDS_TARGET and candidates:
            question = (ASK_LEAVE_TARGET.format() if leaving  # (unescapes {{name}} for Concordia)
                        else ASK_TARGET.format(action=RUNG_OPTIONS[rung.value].lower()))
            target = candidates[0] if len(candidates) == 1 else agent.act(entity_lib.ActionSpec(
                call_to_action=question,
                output_type=entity_lib.OutputType.CHOICE,
                options=tuple(candidates),
            ))

        say = ""
        if rung.value in SPEAKS and target:
            spec = entity_lib.ActionSpec(call_to_action=ask_speech(rung, target, situation),
                                         output_type=entity_lib.OutputType.FREE)
            # The slip check reads the model's whole reply: a quote pulled out of '...it's a serious social
            # science experiment...' must not hide what the model said around it.
            say = self._speak(agent, spec, twin.alias, day)
        return Action(rung, target, say)

    def _speak(self, agent, spec, alias: str, day: int) -> str:
        """One line of speech. Re-asked (up to RESAMPLES times) when it breaks immersion, comes out empty,
        or echoes a line already said in the conversation. Still out of character after that, the whole
        reply goes to the engine, which drops it (#64); still empty or an echo, the last try stands."""
        raw = self._resample_while_breaking(alias, day, lambda: agent.act(spec), lambda reply: reply)
        if immersion.breaking_phrase(raw):
            return raw
        line = _clean_speech(alias, raw)
        for _ in range(RESAMPLES):
            problem = ("empty" if not line else "echo" if echoes(line, self._recent.get(alias, []))
                       else "identity" if self._claims_another_name(alias, line) else "")
            if not problem:
                break
            self.redos.append(Breach(day, alias, problem, line))
            retry = agent.act(spec)
            if not immersion.breaking_phrase(retry):
                line = _clean_speech(alias, retry)
        return line

    def _claims_another_name(self, alias: str, line: str) -> bool:
        """'I'm Lina', said by Amir: a twin speaking as someone else (seen once in live runs)."""
        others = [re.escape(n) for n in self._agents if n != alias]
        return bool(others) and bool(re.search(rf"\bI(?:'m| am) (?:{'|'.join(others)})\b", line))

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
        """Every twin that took part today reflects privately (what was said reached them as it happened,
        through `hear`). A twin that spent the day waiting for someone else's date has nothing new to
        reflect on: in live runs over half of all reflections were those, mostly musing about the place.
        The reflection becomes a memory; ratings are only logged."""
        reflections = []
        took_part = {e.twin for e in events} | {e.target for e in events if e.target}
        for alias, agent in self._agents.items():
            if alias not in took_part:
                continue
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
                self._diaries[alias].add(f"Day {day}: {text}")
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
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    out = ""
    for sentence in sentences[:max_sentences]:  # whole sentences only: 39% of live lines were cut mid-word
        if out and len(out) + 1 + len(sentence) > max_chars:
            break
        out = f"{out} {sentence}".strip()
    if len(out) > max_chars:  # one sentence longer than the cap: end at a word, and say so
        out = out[:max_chars].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
    return out
