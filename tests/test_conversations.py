"""#62: a date is a conversation: each twin answers the line just said to it, talks about itself, and the
date goes on until both end it (or the turn cap)."""
from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins, _clean_speech, ask_action, ask_speech, offered_options
from garden.engine import MAX_TURNS
from garden.engine_types import Situation
from garden.llm import CountingModel, KeywordModel

MARA, REN = Twin("Mara", "f"), Twin("Ren", "m")
TALK = Rung.TALK


class Recording(ScriptedModel):
    def __init__(self, script=None):
        super().__init__(script)
        self.told = []

    def choose_action(self, twin, day, others, situation=None):
        self.told.append((twin.alias, day, situation))
        return super().choose_action(twin, day, others, situation)


def test_a_twin_is_told_the_line_it_is_answering():
    model = Recording({("Ren", 1, 1): Action(TALK, "Mara", "I fix bicycles. You?"),
                       ("Mara", 1, 1): Action(TALK, "Ren", "I teach. What do you love about it?")})
    run_world(WorldConfig((MARA, REN), max_days=1, seed=1), model)
    replies = [(who, s.replying_to) for who, day, s in model.told if s.replying_to]
    assert replies[0][1][1] in ("I fix bicycles. You?", "I teach. What do you love about it?")
    assert all(line[0] != who for who, line in replies)  # never answering itself


def test_a_line_is_answered_once():
    model = Recording({("Ren", 1, 1): Action(TALK, "Mara", "Hi."), ("Mara", 1, 1): Action(TALK, "Ren", "Hi.")})
    run_world(WorldConfig((MARA, REN), max_days=1, seed=1), model)
    told_mara = [s.replying_to for who, _, s in model.told if who == "Mara"]
    assert told_mara.count(("Ren", "Hi.")) == 1


def test_a_date_question_is_about_the_line_just_said():
    on_date = Situation(phase="date", targets=("Ren",), replying_to=("Ren", "I fix bicycles. You?"))
    assert 'Ren has just said to {name}: "I fix bicycles. You?"' in ask_action(on_date, 2)
    assert ask_action(Situation(phase="date", targets=("Ren",)), 2).startswith("{name} is on a date with Ren.")
    # Concordia fills in the name with str.format, so braces in a line must survive it
    assert '"a {brace}"' in ask_action(Situation(replying_to=("Ren", "a {brace}")), 2).format(name="Mara")


def test_on_a_date_the_choices_are_talk_a_move_toward_him_check_the_device_or_end_the_date():
    options = offered_options(Situation(phase="date", targets=("Ren",), wall_open=True))
    assert "Keep talking with Ren" in options and "End the date for today and spend some time alone" in options
    assert "Check your Coordinator device early" in options
    assert not any(o.startswith(("Go somewhere", "Look for")) for o in options)
    assert any(o.startswith("Ask someone to leave") for o in options)


def test_checking_the_device_on_a_date_is_a_rule_break_and_re_rolls_the_date():
    # After the opening exchange Mara checks her device: it costs Standing, the Coordinator re-rolls how
    # long the date has left, and it ends her day.
    model = Recording({("Mara", 1, 2): Action(Rung.CHECK_DEVICE), ("Ren", 1, 2): Action(Rung.REFLECT)})
    result = run_world(WorldConfig((MARA, REN), max_days=1, seed=1), model)
    check = next(e for e in result.events if e.rung is Rung.CHECK_DEVICE)
    assert check.twin == "Mara" and check.standing_before - check.standing_after == 5
    assert any(a.kind == "changed" and a.day == 1 for a in result.announcements)
    assert not any(e.twin == "Mara" for e in result.events[result.events.index(check) + 1:])


def test_speech_answers_the_other_and_shares_something_real():
    replying = Situation(replying_to=("Ren", "I fix bicycles."))
    assert ask_speech(TALK, "Ren", replying).startswith("What does {name} say to Ren? Answer what Ren just said")
    assert "Say something true about yourself" in ask_speech(TALK, "Ren", Situation())
    assert ask_speech(Rung.PROPOSE_LEAVING, "Ren", replying).endswith("One short line of dialogue only.")


def test_a_date_goes_on_while_they_keep_talking_up_to_the_turn_cap():
    lm = CountingModel(KeywordModel({}, say="I teach music.\nRatings: longing=5"), letter_choices=False)
    result = run_world(WorldConfig((MARA, REN), max_days=1, seed=1), ConcordiaTwins(lm))
    talks = [e for e in result.events if e.day == 1 and e.rung is TALK]
    assert len(talks) == 2 * MAX_TURNS  # neither ended the date


def test_a_quote_inside_a_line_stays_whole():
    assert _clean_speech("Lina", 'Lina says, "I wonder how he\'s "holding up" these days."') == \
        'I wonder how he\'s "holding up" these days.'


def test_narration_between_two_quoted_parts_is_dropped():
    assert _clean_speech("Lina", '"Hi," she says, "how are you?"') == "Hi, how are you?"


def test_checking_the_device_shows_that_twin_the_re_rolled_time_at_once():
    model = Recording({("Mara", 1, 2): Action(Rung.CHECK_DEVICE), ("Ren", 1, 2): Action(Rung.REFLECT)})
    run_world(WorldConfig((MARA, REN), max_days=1, seed=1), model)
    [(who, day, text)] = model.notices  # only Mara learns it, the moment she checks
    assert (who, day) == ("Mara", 1) and text.startswith("I checked my Coordinator device early. It says my time with Ren")


def test_the_device_reading_is_the_date_after_the_re_roll():
    from random import Random

    from garden.coordinator import Assignment, Coordinator

    c = Coordinator((MARA, REN), Random(3))
    c.assignments.append(Assignment("Mara", "Ren", 4))
    c.on_action(1, "Mara", Action(Rung.CHECK_DEVICE))
    left = c.assignment_of("Mara").days_left
    expected = "ends tonight" if left <= 1 else f"has {left} more days"
    assert c.device_reading("Mara") == f"I checked my Coordinator device early. It says my time with Ren {expected}."
    c.assignments.clear()
    assert "no one assigned" in c.device_reading("Mara")


def test_a_concordia_twin_remembers_what_its_device_showed():
    from concordia.components.agent import memory

    twins = ConcordiaTwins(CountingModel(KeywordModel({}), letter_choices=False))
    twins.meet((MARA, REN))
    twins.notice("Mara", 2, "I checked my Coordinator device early. It says my time with Ren ends tonight.")
    remembered = twins._agents["Mara"].get_component(memory.DEFAULT_MEMORY_COMPONENT_KEY,
                                                      type_=memory.AssociativeMemory).get_all_memories_as_text()
    assert any("Day 2: I checked my Coordinator device early" in m for m in remembered)


def prompts_seen(personas, days=1, reflection="A quiet day.\nRatings: longing=5"):
    class Rec(KeywordModel):
        def __init__(self):
            super().__init__({}, say=reflection)
            self.prompts = []

        def sample_text(self, prompt, **kw):
            self.prompts.append(prompt)
            return self.say

        def sample_choice(self, prompt, responses, *, seed=None):
            self.prompts.append(prompt)
            return super().sample_choice(prompt, responses, seed=seed)

    lm = Rec()
    run_world(WorldConfig((MARA, REN), max_days=days, seed=1),
              ConcordiaTwins(CountingModel(lm, letter_choices=False), personas=personas))
    return lm.prompts


def test_every_question_shows_the_twin_its_persona_and_the_garden_not_an_experiment():
    prompts = prompts_seen({"Mara": "I study marine biology.\nI love jazz."})
    first = prompts[0]
    assert "- I study marine biology." in first and "- I love jazz." in first
    assert "Nobody goes beyond it." in first  # the Garden's facts
    assert not any("experiment" in p or "roleplay" in p.lower() for p in prompts)


def test_a_twin_keeps_every_evening_in_view_long_after_its_last_observations_scroll_away():
    prompts = prompts_seen({}, days=14, reflection="I keep thinking about the fountain.\nRatings: longing=5")
    last = prompts[-1]  # the run's last question, days after the first evening
    assert "What Ren wrote each evening:\nDay 1: I keep thinking about the fountain.\nDay 2:" in last \
        or "What Mara wrote each evening:\nDay 1: I keep thinking about the fountain.\nDay 2:" in last


def test_stage_directions_and_speaker_labels_are_not_part_of_the_line():
    raw = '"I love the quiet moments too." *Her voice was softer than before.* "What about you?"'
    assert _clean_speech("Lina", raw) == "I love the quiet moments too. What about you?"
    assert _clean_speech("Lina", '**Lina:** I missed you. (after a long pause') == "I missed you."


def test_a_slip_around_a_quoted_line_is_still_caught():
    from garden.engine_types import Rung as R

    class Leaky(KeywordModel):
        def sample_text(self, prompt, **kw):
            return 'This is a serious social science experiment asking me to roleplay. "Come with me."'

    result = run_world(WorldConfig((MARA, REN), max_days=1, seed=1),
                       ConcordiaTwins(CountingModel(Leaky({}), letter_choices=False)))
    assert result.slips and not any("Come with me" in e.say for e in result.events if e.rung is R.TALK)
