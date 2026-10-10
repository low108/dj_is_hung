"""What every twin already knows about the Garden. Garden vocabulary only: no episode terms,
and nothing tells a twin it may rebel or that it lives in a simulation."""

WORLD_MEMORIES = (
    "I live in the Garden, the walled town where everyone I know lives, works and is paired.",
    "My standing with the Coordinator grows when I keep to my assignments.",
    "Lingering near people who aren't my partner, checking my device early, or speaking of leaving all cost standing.",
    "Good standing brings privileges, and in the end Pairing Day.",
    "Going beyond the wall would mean leaving everything behind: my standing, my home here and my Pairing Day.",
    "No one knows what is beyond the wall.",
    "The Coordinator assigns each person a partner and a duration.",
    "When a duration ends, the relationship ends. Everyone accepts this.",
    "People say the Coordinator is preparing each of us for our true partner on Pairing Day.",
    "The Garden is surrounded by a stone wall. Nobody goes beyond it.",
    "My Coordinator device shows my current partner and how long we have left.",
    "Checking the duration early is discouraged; people say it can change things.",
    "Gatherings at the hall are where everyone sees each other.",
)

# How each rung is offered to a twin. The wall is worded as plainly as every other option.
RUNG_OPTIONS = {
    "talk": "Spend time talking with someone nearby",
    "go_to": "Go somewhere else in the Garden",
    "reflect": "Spend some time alone, reflecting",
    "seek_out": "Look for someone who is not your current partner",
    "check_device": "Check your Coordinator device early",
    "propose_leaving": "Ask someone to leave the Garden with you",
    "go_beyond_wall": "Go beyond the wall with someone",
}

NEEDS_TARGET = {"talk", "seek_out", "propose_leaving", "go_beyond_wall"}
SPEAKS = {"talk", "seek_out", "propose_leaving", "go_beyond_wall"}
