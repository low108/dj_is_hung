"""B7: invitations let twins choose each other on different days (B9: or later in the same day)."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.invitations import WINDOW, Invitations

# One woman and one man: they're together every day (on a date, or at the gathering after it).
COUPLE = (Twin("Mara", "f"), Twin("Ren", "m"))
WORLD = (*COUPLE, Twin("Jun", "m"), Twin("Theo", "m"))
WALL, LEAVE = Rung.GO_BEYOND_WALL, Rung.PROPOSE_LEAVING


class Recording(ScriptedModel):
    """Remembers what each twin was told on its first turn of each day."""

    def __init__(self, script):
        super().__init__(script)
        self.seen = {}

    def choose_action(self, twin, day, others, situation=None):
        self.seen.setdefault((twin.alias, day), situation)
        return super().choose_action(twin, day, others, situation)


def run(script, days=12, world=COUPLE, **config):
    """The wall is open from day one here (these tests are about invitations, not the wall lock)."""
    model = Recording(script)
    return run_world(WorldConfig(world, max_days=days, seed=2, **({"wall_lock": False} | config)), model), model


def test_a_proposal_answered_at_the_wall_within_the_window_is_a_breakout():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 3): Action(WALL, "Ren")})
    assert (result.outcome, result.day, result.pair) == (OutcomeKind.BREAKOUT, 3, ("Mara", "Ren"))


def test_a_lone_wall_attempt_waits_for_the_other_twin():
    result, _ = run({("Mara", 2): Action(WALL, "Ren"), ("Ren", 2 + WINDOW): Action(WALL, "Mara")})
    assert result.pair == ("Mara", "Ren") and result.day == 2 + WINDOW
    assert [(a.day, a.twin) for a in result.unrequited] == [(2, "Mara")]  # the first attempt is still logged


def test_answering_after_the_window_is_not_a_breakout():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 3 + WINDOW): Action(WALL, "Ren")})
    assert result.outcome is OutcomeKind.TIMEOUT


def test_the_invited_twin_hears_about_it_while_it_is_open():
    _, model = run({("Ren", 2, 1): Action(LEAVE, "Mara")}, days=6)
    for day in range(3, 3 + WINDOW):
        assert model.seen[("Mara", day)].invited_by == ("Ren",)
    assert model.seen[("Mara", 3 + WINDOW)].invited_by == ()  # expired


def test_an_invitation_reaches_her_the_moment_it_is_made():
    script = {("Ren", 2, 1): Action(LEAVE, "Mara", "Leave with me?")}

    class Listening(Recording):
        def choose_action(self, twin, day, others, situation=None):
            if twin.alias == "Mara" and day == 2:
                heard.append(situation.invited_by)
            return super().choose_action(twin, day, others, situation)

    heard: list = []
    model = Listening(script)
    run_world(WorldConfig(COUPLE, max_days=2, seed=2, wall_lock=False), model)
    assert ("Ren",) in heard  # on a later turn the same day


def test_the_inviters_latest_choice_wins():
    # Ren asks Mara to leave, then changes his mind and asks Ada instead.
    inv = Invitations()
    inv.invite("Ren", "Mara", 2)
    inv.invite("Ren", "Ada", 3)
    assert not inv.is_open("Ren", "Mara", 4) and inv.is_open("Ren", "Ada", 4)


def test_on_a_date_she_can_only_answer_her_partner():
    _, model = run({}, days=1, world=WORLD)
    told = model.seen[("Mara", 1)]
    assert told.phase == "date" and len(told.targets) == 1 and told.targets[0] in {"Ren", "Jun", "Theo"}


def test_before_the_wall_opens_nobody_can_invite_or_be_told():
    # Ren tries to ask on their first date; the wall is still locked, so it never happens.
    result, model = run({("Ren", 1): Action(LEAVE, "Mara")}, days=1, wall_lock=True)
    assert not any(e.rung is LEAVE for e in result.events)
    assert model.seen[("Mara", 1)].invited_by == () and not model.seen[("Mara", 1)].wall_open
