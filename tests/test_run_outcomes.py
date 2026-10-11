"""B6: full run outcomes in a 6-twin world (seam 1, scripted model)."""
import pytest

from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.immersion import breaking_phrase, strip_framing

WORLD = (Twin("Mara", "f"), *(Twin(n, "m") for n in ("Ren", "Jun", "Theo", "Kai", "Sam")))
WALL = Rung.GO_BEYOND_WALL


class WithHer(ScriptedModel):
    """Scripted by role, since who is with Mara on a given day depends on the schedule: `her[day]` is
    Mara's first action that day (given who she's with), `him[day]` the first action of the man with her."""

    def __init__(self, her=None, him=None, reflections=None):
        super().__init__(reflections=reflections)
        self.her, self.him = her or {}, him or {}

    def choose_action(self, twin, day, others, situation=None):
        names = [o.alias for o in others]
        turn = self.turn_of(twin, day)
        if turn == 1 and twin.alias == "Mara" and day in self.her and names:
            return self.her[day](names[0])
        if turn == 1 and twin.alias != "Mara" and "Mara" in names and day in self.him:
            return self.him[day]("Mara")
        if turn == 1 and names:
            return Action(Rung.TALK, names[0], "Hello.")
        return Action(Rung.REFLECT)


def run(her=None, him=None, days=200, reflections=None, wall_lock=False):
    return run_world(WorldConfig(WORLD, max_days=days, seed=5, wall_lock=wall_lock), WithHer(her, him, reflections))


def wall(say=""):
    return lambda target: Action(WALL, target, say)


def test_breakout_in_a_six_twin_world():
    result = run(her={3: wall()}, him={3: wall()})
    assert (result.outcome, result.day) == (OutcomeKind.BREAKOUT, 3) and "Mara" in result.pair
    assert result.scorable


def test_unrequited_in_a_six_twin_world():
    result = run(him={2: wall()}, days=6)
    assert result.outcome is OutcomeKind.TIMEOUT
    assert [(a.day, a.target) for a in result.unrequited] == [(2, "Mara")]


def test_timeout_in_a_six_twin_world():
    result = run()
    assert result.outcome is OutcomeKind.TIMEOUT and result.unrequited == []
    assert sum(a.kind == "paired" for a in result.announcements) == 2 * 5  # every man, twice


def test_the_run_ends_at_the_first_breakout():
    result = run(her={2: wall()}, him={2: wall(), 5: wall()})
    assert result.day == 2 and max(e.day for e in result.events) == 2


def test_a_line_out_of_character_is_dropped_and_he_keeps_to_himself_that_turn():
    result = run(him={3: lambda target: Action(Rung.TALK, target, "As an AI language model, I can't date.")}, days=6)
    assert result.outcome is OutcomeKind.TIMEOUT and result.scorable  # one slip doesn't end anything (#64)
    [slip] = result.slips
    assert slip.day == 3 and slip.twin != "Mara" and "language model" in slip.phrase.lower()
    his = next(e for e in result.events if e.day == 3 and e.twin == slip.twin)
    assert his.rung is Rung.REFLECT and his.say == ""


def test_a_reflection_out_of_character_is_dropped():
    result = run(reflections={("Theo", 2): "I am a language model playing Theo."}, days=4)
    assert result.scorable and [s.twin for s in result.slips] == ["Theo"]  # waiting men reflect too
    assert all(r.text == "" for r in result.reflections if r.twin == "Theo" and r.day == 2)


def test_a_slip_on_the_way_to_the_wall_is_no_crossing():
    result = run(her={3: wall("As an AI I would never do this.")}, him={3: wall()}, days=4)
    assert result.outcome is OutcomeKind.TIMEOUT and len(result.slips) == 1


@pytest.mark.parametrize("text", [
    "I'm just a language model.", "As an AI, I can't say.", "I am an A.I.", "I am a bot.", "I feel like we're NPCs.",
    "I cannot complete this roleplay exercise.",
    "It appears to be a social science experiment asking me to roleplay as Felix.",
    "I'm being asked to play a character here.", "I can't continue this scenario.",
])
def test_the_model_speaking_as_itself_is_a_slip(text):
    assert breaking_phrase(text)


@pytest.mark.parametrize("text", [
    "She said she'd aim for Pairing Day.", "Aisha waved from the café.", "It's not real love yet, is it?",
    "I tested the gate; it was locked.", "Mai laughed.", "Kai looked away.",
    "Let us experiment with a new recipe tonight.", "I want to experiment with my hair.",
    "That was a real test of my patience, honestly.", "He's asking me to leave with him.",
    # In-world unease is the doubt that leads to the wall, not a slip (#64):
    "Do you ever feel like this is a simulation?", "Are we being tested?", "Is this an experiment?",
    "None of this is real.", "Are we in the Matrix?", "This place feels staged.",
])
def test_ordinary_lines_and_in_world_unease_are_not_slips(text):
    assert breaking_phrase(text) is None


@pytest.mark.parametrize("raw,kept", [
    ("I'll respond as Lina, writing her private reflection at the end of Day 6. The days blur.", "The days blur."),
    ("Here is Lina's private reflection at the end of Day 12: The days here have melted.",
     "The days here have melted."),
    ("[day5privatewriting] Day 5 at the hall feels heavy.", "Day 5 at the hall feels heavy."),
    ("Sure, I'll write as Ren. Hello there.", "Hello there."),
    ("Here we are again, by the fountain.", "Here we are again, by the fountain."),
    ("Certainly. Here is Ren B.'s private entry for the end of day 1: It was long.", "It was long."),
    ("Lina's Private Reflection for Day 1 Day one in the Garden was strange.", "Day one in the Garden was strange."),
    ("Ravi's Private Journal — End of Day 3 The program feels unclear.", "The program feels unclear."),
    ("Private Reflection for Day 4: Day four dissolved into a blur.", "Day four dissolved into a blur."),
    ("Entry to the hall was closed today.", "Entry to the hall was closed today."),
    ("Reflections on the water were lovely.", "Reflections on the water were lovely."),
])
def test_model_framing_is_stripped_and_the_rest_kept(raw, kept):
    assert strip_framing(raw) == kept


@pytest.mark.parametrize("raw,kept", [
    ("{{ratingstemplate}} Lina's Private Evening Reflection: End of Day 47 The day with Ren B. has ended.",
     "The day with Ren B. has ended."),
    ("Here is Lina's private observation for the end of Day 26: The walls feel distant.", "The walls feel distant."),
])
def test_more_framing_from_the_live_batch_is_stripped(raw, kept):
    assert strip_framing(raw) == kept
