"""B4: the Coordinator."""
from random import Random

from garden import Action, Rung, ScriptedModel, Twin, WorldConfig, run_world
from garden.coordinator import BONDED, LONG, PLACES, SHORT, Coordinator

WOMAN = Twin("Mara", "f")
MEN = tuple(Twin(n, "m") for n in ("Ren", "Jun", "Theo", "Kai", "Sam"))
WORLD = (WOMAN, *MEN)


def test_every_event_happens_at_a_known_place():
    model = ScriptedModel({
        ("Mara", 1): Action(Rung.SEEK_OUT, "Ren"), ("Ren", 2): Action(Rung.CHECK_DEVICE),
        ("Jun", 2): Action(Rung.GO_TO), ("Mara", 3): Action(Rung.PROPOSE_LEAVING, "Jun"),
        ("Theo", 3): Action(Rung.REFLECT), ("Sam", 4): Action(Rung.GO_BEYOND_WALL, "Mara"),
    })
    result = run_world(WorldConfig(WORLD, max_days=5, seed=1), model)
    assert result.events and all(e.place in PLACES for e in result.events)
    wall = [e for e in result.events if e.rung is Rung.GO_BEYOND_WALL]
    assert all(e.place == "the_wall" for e in wall)


def test_pairs_are_across_genders_so_the_woman_has_one_man_at_a_time():
    c = Coordinator(WORLD, Random(0))
    c.start_day(1, {})
    assert c.partner_of("Mara") in {m.alias for m in MEN}
    assert all("Mara" in (a.first, a.second) for a in c.assignments)  # men are never paired with each other


def test_a_bonded_pair_is_cut_short_and_she_is_next_paired_with_someone_she_is_not_bonded_with():
    c = Coordinator(WORLD, Random(3))
    c.start_day(1, {})
    first = c.partner_of("Mara")
    c.assignment_of("Mara").days_left = 4
    bond = {"Mara": {first: BONDED + 1}, first: {"Mara": BONDED + 1}}
    c.start_day(2, bond)
    assert c.assignment_of("Mara").days_left <= SHORT[1]  # cut short
    for _ in range(SHORT[1]):
        c.end_day()
    c.start_day(5, bond)
    assert c.partner_of("Mara") not in (None, first)  # separated from the one she bonded with


def test_an_unbonded_new_pair_gets_a_long_duration():
    c = Coordinator(WORLD, Random(1))
    c.start_day(1, {})
    assert LONG[0] <= c.assignment_of("Mara").days_left <= LONG[1]


def test_gatherings_happen():
    days = 0
    for seed in range(20):
        c = Coordinator(WORLD, Random(seed))
        c.start_day(1, {})
        days += c.gathering_today
    assert 2 <= days <= 12  # about 30% of days


def test_the_same_seed_gives_the_same_assignments_and_announcements():
    model = ScriptedModel({("Mara", 2): Action(Rung.CHECK_DEVICE)})
    a = run_world(WorldConfig(WORLD, max_days=6, seed=9), model)
    b = run_world(WorldConfig(WORLD, max_days=6, seed=9), model)
    assert a.announcements == b.announcements
    assert [e.place for e in a.events] == [e.place for e in b.events]


def test_her_first_partner_varies_across_runs():
    firsts = set()
    for seed in range(12):
        c = Coordinator(WORLD, Random(seed))
        c.start_day(1, {})
        firsts.add(c.partner_of("Mara"))
    assert len(firsts) >= 3


def test_checking_the_device_early_reshuffles_the_time_left():
    c = Coordinator(WORLD, Random(5))
    c.start_day(1, {})
    seen = set()
    for _ in range(10):
        c.on_action(1, "Mara", Action(Rung.CHECK_DEVICE))
        seen.add(c.assignment_of("Mara").days_left)
    assert len(seen) > 1
    assert any("changed" in a.text for a in c.announcements)


def test_twins_are_told_their_assignment_in_words():
    c = Coordinator(WORLD, Random(2))
    c.start_day(1, {})
    partner = c.partner_of("Mara")
    assert partner in c.describe("Mara")
    unassigned = next(m.alias for m in MEN if c.partner_of(m.alias) is None)
    assert "between assignments" in c.describe(unassigned)


# --- through the run_world seam -------------------------------------------------------------

def _pairings(result, who="Mara"):
    """(day, partner) for every new pairing announced for `who`."""
    out = []
    for a in result.announcements:
        if "paired for" in a.text and who in a.text:
            names = a.text.split(":")[0].split(" and ")
            out.append((a.day, next(n for n in names if n != who)))
    return out


def test_through_runs_a_twin_she_bonded_with_is_not_paired_with_her_again():
    for seed in range(50):
        # Mara seeks out Ren every day; everyone else keeps to themselves, so only Mara and Ren bond.
        quiet = {(m.alias, d): Action(Rung.REFLECT) for m in MEN for d in range(1, 13)}
        model = ScriptedModel(quiet | {("Mara", d): Action(Rung.SEEK_OUT, "Ren") for d in range(1, 13)})
        result = run_world(WorldConfig(WORLD, max_days=12, seed=seed), model)
        bonded_from = 3  # two days of seeking out = bond 2 (BONDED)
        later = [partner for day, partner in _pairings(result) if day > bonded_from]
        assert "Ren" not in later, (seed, _pairings(result))


def test_through_runs_everyone_is_at_the_hall_on_a_gathering_day():
    model = ScriptedModel({("Ren", d): Action(Rung.REFLECT) for d in range(1, 11)}
                          | {("Jun", d): Action(Rung.GO_TO) for d in range(1, 11)})
    result = run_world(WorldConfig(WORLD, max_days=10, seed=4), model)
    gathering_days = {a.day for a in result.announcements if "gathering" in a.text}
    assert gathering_days
    for e in result.events:
        if e.day in gathering_days:
            assert e.place == "gathering_hall", e


def test_checking_the_device_never_lengthens_a_bonded_pairing():
    c = Coordinator(WORLD, Random(8))
    c.start_day(1, {})
    partner = c.partner_of("Mara")
    c.start_day(2, {"Mara": {partner: BONDED}, partner: {"Mara": BONDED}})
    for _ in range(20):
        c.on_action(2, "Mara", Action(Rung.CHECK_DEVICE))
        assert c.assignment_of("Mara").days_left <= SHORT[1]
