"""Demo scenes: date venues and gist emoji are picked from fixed lists and added to recorded events."""
from garden.scenes import DATE_VENUES, GIST, Scene, apply, date_days, top_gist


def test_the_gist_is_up_to_three_emoji_close_to_the_best():
    probs = {"❤️": 0.4, "😊": 0.3, "🎵": 0.21, "🏀": 0.09}
    assert top_gist(probs) == ["❤️", "😊", "🎵"]
    assert top_gist({"❤️": 0.8, "😊": 0.1, "🎵": 0.1}) == ["❤️"]  # one clear winner shows alone
    assert top_gist({}) == []


def test_dates_are_grouped_by_day_and_pair_and_gatherings_are_not_dates():
    events = [{"seq": 1, "day": 1, "twin": "Lina", "target": "Ravi", "place": "cafe", "say": "Hi"},
              {"seq": 2, "day": 1, "twin": "Ravi", "target": "Lina", "place": "cafe", "say": "Hello"},
              {"seq": 3, "day": 4, "twin": "Lina", "target": "Kenji", "place": "gathering_hall", "say": "Hey"},
              {"seq": 4, "day": 1, "twin": "Lina", "target": None, "place": "home", "say": ""}]
    assert list(date_days(events)) == [(1, frozenset({"Lina", "Ravi"}))]


def test_apply_adds_venue_and_gist_only_where_decided():
    events = [{"seq": 1, "say": "Hi"}, {"seq": 2, "say": ""}]
    out = apply(events, Scene({1: "court"}, {1: ["🏀", "😂"]}))
    assert out[0] == {"seq": 1, "say": "Hi", "venue": "court", "gist": ["🏀", "😂"]} and out[1] == events[1]


def test_every_venue_and_emoji_has_a_description():
    assert all(len(v) == 3 and v[2] for v in DATE_VENUES.values()) and all(GIST.values())
    assert {"court", "kitchen", "cinema", "river", "trail"} <= set(DATE_VENUES)
