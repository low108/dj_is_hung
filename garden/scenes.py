"""Scenes for the demo map: where each date happens and what each line is about, as emoji.

The engine knows six places (home, café, park, gathering hall, the Coordinator's office, the wall), but
twins talk about far more: courts, kitchens, movie nights, rivers, trails. A recorded run is annotated
once, after the fact, so the map can show those venues and each speech bubble shows up to three emoji
instead of the whole line (the full text stays in her log). Both are type-safe ChoiceQuestions for the
MediaPipe Decision Maker (garden/decisions.py): the answer is always a venue or emoji on the list.

Venues come from what the twins actually said: across 3,606 lines and 2,767 diaries, the shared
activities were sports courts (court 117, pitch 43), kitchens (192), movie and concert nights (movie
140, concert 112), flowers (83), the river (79), trails (50), the bakery (26) and the museum (47).
"""
from __future__ import annotations

from dataclasses import dataclass

# Where a date can be, beyond the engine's places: key -> (label, emoji, what happens there).
DATE_VENUES = {
    "cafe": ("Café", "☕", "Coffee and small talk at a café table; a first, getting-to-know-you conversation."),
    "park": ("Park", "🌳", "Strolling on the lawns or sitting on a park bench; an easy, open-air chat."),
    "kitchen": ("Kitchen", "🍳", "Cooking together or sharing a dinner: recipes, food, a meal at the table."),
    "court": ("Sports court", "🏀", "Playing basketball, tennis or football, a race or a rematch on the court."),
    "cinema": ("Cinema & stage", "🎬", "A movie night, a concert, singing a song or dancing on the stage."),
    "flower_garden": ("Flower garden", "🌸", "Among the flowers: sketching, drawing, a quiet walk among blooms."),
    "river": ("Riverside", "🌊", "Walking by the river or the lake, watching the sunrise or the sunset."),
    "trail": ("Hiking trail", "🥾", "Hiking a trail up the ridge or a hill, a dawn walk, a climb."),
    "bakery": ("Bakery street", "🥐", "The bakery and the market street: pastries, a morning stroll, errands."),
    "museum": ("Museum", "🖼️", "Visiting the museum or a gallery: exhibits, paintings, art and history."),
}
DATE_QUESTION = "Where in the Garden are these two spending their date today?"

# What a line can be about, as emoji: emoji -> meaning. A bubble shows the top three that fit.
GIST = {
    "❤️": "love, affection, falling for someone", "🥺": "longing, missing someone", "😊": "happy, warm, glad",
    "😂": "laughing, joking, teasing fun", "😏": "flirting, playful teasing", "😳": "shy, nervous, embarrassed",
    "😢": "sad, hurt, tearful", "😟": "worried, anxious, afraid", "💔": "heartbreak, rejection, saying no",
    "🤔": "asking a question, curious, wondering", "🙏": "hoping, asking a favour, please",
    "🤝": "a promise, a deal, an agreement", "✅": "yes, agreeing, accepting", "🙅": "no, refusing, declining",
    "💌": "asking someone to leave the Garden together", "🧱": "the wall, going beyond the wall",
    "🚪": "leaving, walking away, goodbye", "⏰": "time running out, the timer, deadlines",
    "📱": "the Coordinator's device, checking the device", "🎯": "Pairing Day, the Coordinator's verdict",
    "🎬": "movies, films, a movie night", "🎵": "music, a song, a concert, singing", "💃": "dancing",
    "🏀": "basketball, a court, a game", "🎾": "tennis", "⚽": "football, soccer, a pitch",
    "🏃": "running, a race, training", "🥾": "hiking, a trail, a climb", "🌅": "sunrise, sunset, dawn",
    "🌊": "a river, a lake, the sea", "🌸": "flowers, a garden", "🎨": "drawing, sketching, painting, art",
    "🖼️": "a museum, a gallery, an exhibit", "📚": "books, studying, reading, school", "⚖️": "law, a court case, a verdict",
    "💼": "work, a job, finance, business", "🍳": "cooking, a kitchen, a recipe", "🍝": "dinner, food, a meal",
    "☕": "coffee, a café", "🥐": "a bakery, pastries", "🍷": "wine, drinks, a toast", "✈️": "travel, a faraway country",
    "🏠": "home, where they grew up", "👪": "family, parents, children", "✉️": "a letter, writing, a note",
    "🎁": "a surprise, a gift", "🏆": "winning, a bet, a competition", "🌙": "night, the stars, the moon",
    "🔥": "passion, excitement, being bold", "😴": "tired, quiet, resting",
}
GIST_QUESTION = "Which emoji best sums up what this line says?"
GIST_MAX = 3
GIST_SHARE = 0.5  # a second or third emoji shows only if at least this share of the top one's probability


@dataclass(frozen=True)
class Scene:
    venue: dict[int, str]       # event seq -> date venue key (date events only)
    gist: dict[int, list[str]]  # event seq -> up to GIST_MAX emoji (events with a line)


def top_gist(probabilities: dict[str, float], k: int = GIST_MAX, share: float = GIST_SHARE) -> list[str]:
    """The most likely emoji, then up to k-1 more that score at least `share` of the top one."""
    ranked = sorted(probabilities, key=probabilities.get, reverse=True)
    if not ranked:
        return []
    best = probabilities[ranked[0]]
    return [e for e in ranked[:k] if probabilities[e] >= share * best]


def date_days(events: list[dict], woman: str | None = None) -> dict[tuple[int, frozenset], list[dict]]:
    """The lines of each date, by (day, the two twins): the events that happen 'on a date' in a place
    the engine calls the café or the park (gatherings are at the hall, leaving is at the wall)."""
    days: dict[tuple[int, frozenset], list[dict]] = {}
    for e in events:
        if e.get("twin") and e.get("target") and e.get("place") in ("cafe", "park"):
            days.setdefault((e["day"], frozenset((e["twin"], e["target"]))), []).append(e)
    return days


def annotate(events: list[dict], maker=None) -> Scene:
    """Venues for every date day and gist emoji for every line, decided by the Decision Maker."""
    from mediapipe.tasks.python.decision import decision_maker as dm

    from .decisions import DEFAULT, _maker

    maker = maker or _maker(DEFAULT)
    where = dm.ChoiceQuestion(criteria={k: v[2] for k, v in DATE_VENUES.items()}, instructions=DATE_QUESTION,
                              normalize_prior=True)
    what = dm.ChoiceQuestion(criteria=GIST, instructions=GIST_QUESTION, normalize_prior=True)
    maker.prewarm_choice(where)
    maker.prewarm_choice(what)
    venue: dict[int, str] = {}
    for (day, pair), lines in date_days(events).items():
        talk = "\n".join(f'{e["twin"]}: "{e["say"]}"' for e in lines if e.get("say"))[-6000:]
        if talk:
            key = maker.evaluate_choice(f"Day {day}, a date between {' and '.join(sorted(pair))}.\n{talk}", where).selected_key
            venue.update({e["seq"]: key for e in lines})
    gist = {}
    for e in events:
        if e.get("say"):
            result = maker.evaluate_choice(f'{e["twin"]} says to {e.get("target") or "someone"}: "{e["say"]}"', what)
            gist[e["seq"]] = top_gist(dict(result.probabilities))
    return Scene(venue, gist)


def apply(events: list[dict], scene: Scene) -> list[dict]:
    """The events with 'venue' (dates only) and 'gist' (lines only) added."""
    out = []
    for e in events:
        extra = {}
        if e["seq"] in scene.venue:
            extra["venue"] = scene.venue[e["seq"]]
        if e["seq"] in scene.gist:
            extra["gist"] = scene.gist[e["seq"]]
        out.append(e | extra)
    return out
