"""B7: invitations let twins choose each other on different days (B9: or later in the same day). An
invitation stays open until it is answered or the inviter invites someone else, and asking back counts
as an answer."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.invitations import Invitations

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


def test_a_proposal_answered_at_the_wall_is_a_breakout():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 3): Action(WALL, "Ren")})
    assert (result.outcome, result.day, result.pair) == (OutcomeKind.BREAKOUT, 3, ("Mara", "Ren"))


def test_a_lone_wall_attempt_waits_for_the_other_twin():
    result, _ = run({("Mara", 2): Action(WALL, "Ren"), ("Ren", 4): Action(WALL, "Mara")})
    assert result.pair == ("Mara", "Ren") and result.day == 4
    assert [(a.day, a.twin) for a in result.unrequited] == [(2, "Mara")]  # the first attempt is still logged


def test_an_invitation_answered_days_later_is_still_a_breakout():
    # In live runs a 2-day window expired before he had a turn again; now it waits for the answer.
    # (The old 2-day window closed after day 4; a lone couple runs out of dates around day 6.)
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 5): Action(WALL, "Ren")})
    assert (result.outcome, result.day) == (OutcomeKind.BREAKOUT, 5)


def test_asking_back_answers_an_invitation():
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Mara", 5): Action(LEAVE, "Ren", "Yes. Let's go.")})
    assert (result.outcome, result.day, result.pair) == (OutcomeKind.BREAKOUT, 5, ("Mara", "Ren"))


def test_two_twins_asking_each_other_the_same_day_break_out():
    # Seed 14 of the live batch: Lina and Amir asked each other on day 25 and nothing happened.
    result, _ = run({("Ren", 3, 1): Action(LEAVE, "Mara", "Come with me?"), ("Mara", 3, 1): Action(LEAVE, "Ren", "Leave with me?")})
    assert (result.outcome, result.day) == (OutcomeKind.BREAKOUT, 3)


def test_inviting_someone_else_withdraws_the_invitation():
    world = (*COUPLE, Twin("Ada", "f"))
    result, _ = run({("Ren", 2): Action(LEAVE, "Mara"), ("Ren", 4): Action(LEAVE, "Ada"),
                     ("Mara", 6): Action(WALL, "Ren")}, days=7, world=world)
    assert result.outcome is OutcomeKind.TIMEOUT  # Ren had asked Ada by then


def test_the_invited_twin_hears_about_it_until_it_is_answered():
    _, model = run({("Ren", 2, 1): Action(LEAVE, "Mara")}, days=6)
    for day in range(3, 6):
        assert model.seen[("Mara", day)].invited_by == ("Ren",)


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
