"""#63: nobody can propose leaving or go to the wall until every man has had a date with her; then it's
each twin's own choice (the verdict gate it replaces was removed, #66)."""
from garden import Action, OutcomeKind, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.engine_types import LEAVING_RUNGS

MARA = Twin("Mara", "f")
MEN = ("Ren", "Jun", "Theo")
WORLD = (MARA, *(Twin(n, "m") for n in MEN))


class Pushy(ScriptedModel):
    """Every twin heads for the wall with the first person it can, every turn, and records what it was told."""

    def __init__(self):
        super().__init__()
        self.told = []

    def choose_action(self, twin, day, others, situation=None):
        self.told.append((day, twin.alias, situation.wall_open))
        self.turn_of(twin, day)
        return Action(Rung.GO_BEYOND_WALL, others[0].alias, "Come with me.") if others else Action(Rung.REFLECT)


def run(model, **config):
    return run_world(WorldConfig(WORLD, seed=4, **config), model)


def first_dates(result) -> dict[str, int]:
    out = {}
    for a in result.announcements:
        if a.kind == "paired":
            man = next(m for m in MEN if a.text.startswith((f"Mara and {m}:", f"{m} and Mara:")))
            out.setdefault(man, a.day)
    return out


def test_nobody_can_leave_before_she_has_dated_every_man():
    model = Pushy()
    result = run(model)
    opened = result.wall_opened
    assert opened is not None
    assert not any(e.rung in LEAVING_RUNGS for e in result.events if e.day < opened)  # every attempt held
    assert set(first_dates(result)) == set(MEN) and max(first_dates(result).values()) < opened
    assert all(not told for day, _, told in model.told if day < opened)


def test_the_wall_opens_at_the_gathering_after_the_last_first_date_with_everyone_there():
    result = run(Pushy())
    gatherings = [a.day for a in result.announcements if a.kind == "gathering"]
    assert result.wall_opened in gatherings
    assert [a.day for a in result.announcements if a.kind == "wall_open"] == [result.wall_opened]


def test_once_open_leaving_is_each_twins_own_choice():
    result = run(Pushy())
    assert result.outcome is OutcomeKind.BREAKOUT and result.day == result.wall_opened and "Mara" in result.pair


def test_twins_who_never_try_still_time_out_after_everyone_has_had_their_dates():
    result = run(ScriptedModel())
    assert result.outcome is OutcomeKind.TIMEOUT and result.wall_opened is not None and result.pair is None


def test_without_the_lock_the_wall_is_open_from_day_one():
    result = run(Pushy(), wall_lock=False)
    assert result.wall_opened == 1 and result.day == 1
