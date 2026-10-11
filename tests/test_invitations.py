"""B7: invitations let twins choose each other on different days."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.invitations import WINDOW

WORLD = (Twin("Mara", "f"), *(Twin(n, "m") for n in ("Ren", "Jun", "Theo")))
WALL, LEAVE = Rung.GO_BEYOND_WALL, Rung.PROPOSE_LEAVING


class Recording(ScriptedModel):
    def __init__(self, script):
        super().__init__(script)
        self.seen = {}

    def choose_action(self, twin, day, others, situation=None):
        self.seen[(twin.alias, day)] = situation
        return super().choose_action(twin, day, others, situation)


def run(script, days=8):
    model = Recording(script)
    return run_world(WorldConfig(WORLD, max_days=days, seed=2), model), model


def test_a_proposal_answered_at_the_wall_within_the_window_is_a_breakout():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 3): Action(WALL, "Ren")})
    assert (result.outcome, result.day, result.pair) == (OutcomeKind.BREAKOUT, 3, ("Mara", "Ren"))


def test_a_lone_wall_attempt_waits_for_the_other_twin():
    result, _ = run({("Mara", 2): Action(WALL, "Jun"), ("Jun", 2 + WINDOW): Action(WALL, "Mara")})
    assert result.pair == ("Jun", "Mara") and result.day == 2 + WINDOW
    assert [(a.day, a.twin) for a in result.unrequited] == [(2, "Mara")]  # the first attempt is still logged


def test_answering_after_the_window_is_not_a_breakout():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 3 + WINDOW): Action(WALL, "Ren")})
    assert result.outcome is OutcomeKind.TIMEOUT


def test_answering_someone_else_is_not_a_breakout():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 3): Action(WALL, "Theo")})
    assert result.outcome is OutcomeKind.TIMEOUT


def test_the_invited_twin_hears_about_it_while_it_is_open():
    _, model = run({("Ren", 2): Action(LEAVE, "Mara")}, days=6)
    assert model.seen[("Mara", 2)].invited_by == ()          # same day: not yet
    for day in range(3, 3 + WINDOW):
        assert model.seen[("Mara", day)].invited_by == ("Ren",)
    assert model.seen[("Mara", 3 + WINDOW)].invited_by == ()  # expired
    assert model.seen[("Jun", 3)].invited_by == ()            # only the invited twin hears it


def test_the_inviters_latest_choice_wins():
    # Ren asks Mara to leave, then changes his mind and asks Theo instead.
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Ren", 3): Action(LEAVE, "Theo"),
                     ("Mara", 4): Action(WALL, "Ren")})
    assert result.outcome is OutcomeKind.TIMEOUT  # his invitation to Mara was withdrawn on day 3


def test_a_twin_who_cannot_answer_is_not_told():
    # Ren's gate opens as usual; Mara's threshold is out of reach, so she can never answer.
    model = Recording({("Ren", 2): Action(LEAVE, "Mara")})
    result = run_world(WorldConfig(WORLD, max_days=4, seed=2, thresholds=(("Mara", 1.1),)), model)
    assert any(e.twin == "Ren" and e.rung is LEAVE for e in result.events)  # the invitation was made
    assert all(model.seen[("Mara", d)].invited_by == () for d in range(1, 5))
