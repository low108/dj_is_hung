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


def test_on_a_date_the_choices_are_keep_talking_a_move_toward_him_or_end_the_date():
    options = offered_options(Situation(phase="date", targets=("Ren",), wall_open=True))
    assert "Keep talking with Ren" in options and "End the date for today and spend some time alone" in options
    assert not any(o.startswith(("Go somewhere", "Check your Coordinator", "Look for")) for o in options)
    assert any(o.startswith("Ask someone to leave") for o in options)


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
