"""Leaving is about someone: she can ask anyone she has met, not only today's date; each twin keeps what
each person said to it; and staying has a real promise (Pairing Day)."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.concordia_twins import ConcordiaTwins, offered_options
from garden.engine_types import Situation
from garden.llm import CountingModel, KeywordModel

LINA = Twin("Lina", "f")
MEN = (Twin("Felix", "m"), Twin("Amir", "m"), Twin("Kenji", "m"))
WORLD = (LINA, *MEN)


class AsksFelix(ScriptedModel):
    """Lina asks Felix to leave on her first turn once the wall is open, wherever he is; Felix accepts
    the first time he can act. Everyone else just chats."""

    def __init__(self):
        super().__init__()
        self.asked_on = None
        self.dates = []

    def choose_action(self, twin, day, others, situation=None):
        if twin.alias == "Lina" and situation and situation.phase == "date" and self.asked_on is None:
            self.dates.append(others[0].alias if others else None)
        if (twin.alias == "Lina" and situation and situation.wall_open and self.asked_on is None
                and "Felix" in (situation.leave_targets or ())):
            self.asked_on = day
            self.turn_of(twin, day)
            return Action(Rung.PROPOSE_LEAVING, "Felix", "Leave with me, Felix.")
        if twin.alias == "Felix" and situation and "Lina" in situation.invited_by:
            self.turn_of(twin, day)
            return Action(Rung.GO_BEYOND_WALL, "Lina", "Yes.")
        return super().choose_action(twin, day, others, situation)


def test_she_can_ask_a_man_she_met_before_even_on_a_date_with_someone_else():
    model = AsksFelix()
    result = run_world(WorldConfig(WORLD, seed=3), model)
    ask = next(e for e in result.events if e.twin == "Lina" and e.rung is Rung.PROPOSE_LEAVING)
    assert ask.target == "Felix"  # not turned into keeping to herself, though Felix wasn't with her
    assert result.outcome is OutcomeKind.BREAKOUT and set(result.pair) == {"Lina", "Felix"}


def test_she_cannot_ask_someone_she_has_never_met():
    config = WorldConfig(WORLD, seed=3, wall_lock=False, max_days=1)
    first_date = next(e.target for e in run_world(config, ScriptedModel()).events if e.twin == "Lina")
    stranger = next(m.alias for m in MEN if m.alias != first_date)  # on day 1 she has met only her date
    result = run_world(config, ScriptedModel({("Lina", 1): Action(Rung.PROPOSE_LEAVING, stranger, "Come?")}))
    assert not any(e.rung is Rung.PROPOSE_LEAVING for e in result.events)


def test_leaving_is_offered_and_asked_about_as_love():
    options = offered_options(Situation(phase="date", targets=("Felix",), wall_open=True))
    assert "Ask the one you love to leave the Garden with you" in options
    assert "Go beyond the wall with the one you love" in options


def test_a_concordia_twin_chooses_who_to_leave_with_from_everyone_it_has_met():
    class Recorder(KeywordModel):
        def __init__(self):
            super().__init__({"do now": "the one you love"}, say="A day.\nRatings: longing=5")
            self.leave_questions = []

        def sample_choice(self, prompt, responses, *, seed=None):
            question = prompt[prompt.rfind("Question:"):]
            if "love enough to leave the Garden with" in question:
                self.leave_questions.append(question)
            return super().sample_choice(prompt, responses, seed=seed)

    lm = Recorder()
    run_world(WorldConfig(WORLD, seed=3, max_days=40, max_turns=3),
              ConcordiaTwins(CountingModel(lm, letter_choices=False)))
    asked = [q for q in lm.leave_questions if q.startswith("Question: Of everyone Lina has met")]
    assert asked and all(m.alias in asked[0] for m in MEN)  # every man she has met is a choice
    assert not any("{name}" in q for q in lm.leave_questions)


def test_each_twin_remembers_what_each_person_said_to_it_under_their_name():
    personas = {"Lina": "I study law.", "Felix": "I grew up in Southern California.", "Amir": "I am from Miami."}

    class Speaker(KeywordModel):
        def sample_text(self, prompt, **kw):
            if "writes privately" in prompt[-800:]:
                return "A day.\nRatings: longing=5"
            who = prompt[prompt.rfind("Answer:") + 7:].strip()
            return {"Felix": "I grew up in Southern California, by the sea.", "Amir": "Miami taught me to swim.",
                    "Kenji": "Buenos Aires is loud.", "Lina": f"Tell me more, {len(prompt) % 97}."}.get(who, "Hi.")

    twins = ConcordiaTwins(CountingModel(Speaker({}), letter_choices=False), personas=personas)
    run_world(WorldConfig(WORLD, seed=3, max_days=12, max_turns=3), twins)
    people = twins._people["Lina"].get_state()["state"]
    felix = next(line for line in people.splitlines() if line.startswith("Felix"))
    assert "Southern California" in felix and "Miami" not in felix  # his words, under his name only
    assert "Southern California" not in twins._people["Amir"].get_state()["state"]  # Amir never heard Felix


def test_staying_has_a_real_promise_and_pairing_day_arrives():
    prompts = []

    class Rec(KeywordModel):
        def sample_choice(self, prompt, responses, *, seed=None):
            prompts.append(prompt)
            return super().sample_choice(prompt, responses, seed=seed)

    result = run_world(WorldConfig(WORLD, seed=3), ConcordiaTwins(CountingModel(Rec({}, say="Hi."), letter_choices=False)))
    assert "true partner for life: a home, a family and a future together" in prompts[0]
    assert result.outcome is OutcomeKind.TIMEOUT
    assert [a.kind for a in result.announcements][-1] == "pairing_day"
