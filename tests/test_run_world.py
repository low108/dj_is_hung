"""Seam 1: a simulation run, driven by the scripted fake model. B9: natural days (dates, gatherings,
conversations that go on until both stop)."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.coordinator import DATES_EACH
from garden.engine import MAX_TURNS

MARA, REN = Twin("Mara", "f"), Twin("Ren", "m")
POOL = (MARA, REN, Twin("Jun", "m"), Twin("Theo", "m"))
WALL, TALK, LEAVE = Rung.GO_BEYOND_WALL, Rung.TALK, Rung.PROPOSE_LEAVING


def world(*twins, max_days=200, wall_lock=False):
    """The wall is open from day one unless asked (the wall lock has its own tests)."""
    return WorldConfig(twins=tuple(twins), max_days=max_days, seed=7, wall_lock=wall_lock)


def gathering_days(result) -> list[int]:
    return [a.day for a in result.announcements if a.kind == "gathering"]


def test_both_choose_the_wall_is_a_breakout_and_the_run_ends():
    # With one man, Mara and Ren are together every day (on a date or at the gathering).
    model = ScriptedModel({("Mara", 4): Action(WALL, "Ren"), ("Ren", 4): Action(WALL, "Mara")})
    result = run_world(world(MARA, REN), model)
    assert (result.outcome, result.day, result.pair) == (OutcomeKind.BREAKOUT, 4, ("Mara", "Ren"))
    assert max(e.day for e in result.events) == 4


def test_a_proposal_can_be_answered_the_same_day():
    model = ScriptedModel({("Ren", 3, 1): Action(LEAVE, "Mara", "Leave with me."),
                           ("Mara", 3, 1): Action(TALK, "Ren", "Now?"), ("Mara", 3, 2): Action(WALL, "Ren")})
    result = run_world(world(MARA, REN), model)
    assert (result.outcome, result.day) == (OutcomeKind.BREAKOUT, 3)


def test_one_twin_choosing_the_wall_is_unrequited_and_the_run_continues():
    result = run_world(world(MARA, REN, max_days=6), ScriptedModel({("Ren", 3): Action(WALL, "Mara")}))
    assert result.outcome is OutcomeKind.TIMEOUT and result.day == 6
    assert [(a.day, a.twin, a.target) for a in result.unrequited] == [(3, "Ren", "Mara")]


def test_no_wall_choice_times_out_at_the_safety_cap():
    result = run_world(world(MARA, REN, max_days=5), ScriptedModel())
    assert (result.outcome, result.day, result.pair, result.unrequited) == (OutcomeKind.TIMEOUT, 5, None, [])


def test_on_a_date_only_the_pair_acts_and_only_toward_each_other():
    result = run_world(world(*POOL), ScriptedModel())
    gatherings = set(gathering_days(result))
    for day in {e.day for e in result.events} - gatherings:
        acting = {e.twin for e in result.events if e.day == day}
        assert len(acting) == 2 and "Mara" in acting
        assert all(e.target in acting - {e.twin} for e in result.events if e.day == day and e.target)


def test_men_waiting_for_their_date_still_reflect_every_evening():
    result = run_world(world(*POOL), ScriptedModel())
    day_one = {r.twin for r in result.reflections if r.day == 1}
    assert day_one == {"Mara", "Ren", "Jun", "Theo"}


def test_a_gathering_follows_every_date_and_everyone_acts_toward_the_opposite_sex():
    result = run_world(world(*POOL), ScriptedModel())
    ended = [a.day for a in result.announcements if a.kind == "ended"]
    assert ended and gathering_days(result) == ended  # the last date's gathering is a last chance
    gender = {t.alias: t.gender for t in POOL}
    for day in gathering_days(result):
        todays = [e for e in result.events if e.day == day]
        assert {e.twin for e in todays} == {t.alias for t in POOL}  # everyone is at the hall
        assert all(gender[e.target] != gender[e.twin] for e in todays if e.target)


def test_a_conversation_goes_on_until_both_stop():
    script = {**{("Mara", 1, n): Action(TALK, "Ren", f"Mara {n}") for n in (1, 2, 3)},
              **{("Ren", 1, n): Action(TALK, "Mara", f"Ren {n}") for n in (1, 2, 3)}}
    result = run_world(world(MARA, REN), ScriptedModel(script))
    day_one = [(e.twin, e.rung) for e in result.events if e.day == 1]
    talks = [who for who, rung in day_one if rung is TALK]
    assert len(talks) == 6 and all(a != b for a, b in zip(talks, talks[1:]))  # they answer each other
    assert [rung for _, rung in day_one[-2:]] == [Rung.REFLECT, Rung.REFLECT]  # then both stop


def test_a_twin_has_at_most_max_turns_a_day():
    class Chatty(ScriptedModel):
        def choose_action(self, twin, day, others, situation=None):
            self.turn_of(twin, day)
            return Action(TALK, others[0].alias, "And another thing...") if others else Action(Rung.REFLECT)

    result = run_world(world(MARA, REN, max_days=1), Chatty())
    assert len([e for e in result.events if e.twin == "Mara"]) == MAX_TURNS


def test_the_run_ends_when_every_man_has_had_his_dates():
    result = run_world(world(*POOL), ScriptedModel())
    assert result.outcome is OutcomeKind.TIMEOUT and result.day < 200
    paired = [a.text for a in result.announcements if a.kind == "paired"]
    for man in ("Ren", "Jun", "Theo"):
        assert sum(man in text for text in paired) == DATES_EACH


def test_acting_toward_someone_out_of_reach_is_keeping_to_oneself():
    # On a date, Mara can't go to the wall for anyone but her partner (after they've both spoken).
    result = run_world(world(*POOL), ScriptedModel({("Mara", 1, 2): Action(WALL, "Nobody")}))
    second = [e for e in result.events if e.day == 1 and e.twin == "Mara"][1]
    assert second.rung is Rung.REFLECT and result.unrequited == []


def test_a_twin_can_follow_someone_to_the_wall_after_they_have_left_for_the_day():
    # Whoever goes first heads for the wall (ending their day); the other still chooses the wall for them.
    model = ScriptedModel({("Mara", 2): Action(WALL, "Ren"), ("Ren", 2): Action(WALL, "Mara")})
    assert run_world(world(MARA, REN), model).day == 2


def test_nobody_can_talk_to_someone_who_has_left_for_the_day():
    script = {("Mara", 1, 2): Action(Rung.REFLECT), **{("Ren", 1, n): Action(TALK, "Mara", "Wait!") for n in (1, 2, 3)}}
    day_one = [e for e in run_world(world(MARA, REN), ScriptedModel(script)).events if e.day == 1]
    left = next(i for i, e in enumerate(day_one) if e.twin == "Mara" and e.rung is Rung.REFLECT)
    assert all(e.rung is not TALK for e in day_one[left + 1:] if e.twin == "Ren")  # his words go nowhere


def test_a_date_opens_with_both_speaking_before_either_can_withdraw():
    script = {("Mara", 1, 1): Action(Rung.REFLECT), ("Ren", 1, 1): Action(Rung.REFLECT)}
    day_one = [e for e in run_world(world(MARA, REN), ScriptedModel(script)).events if e.day == 1]
    firsts = {e.twin: e for e in reversed(day_one)}  # each twin's first turn
    assert all(e.rung is TALK and e.target != e.twin for e in firsts.values())  # turned into talking
